from datetime import timedelta
import random
import string
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken

from django.core import signing
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from .football_data import fetch_pl_matches, fetch_pl_scorers
from .models import AdminProfile, TransferRecord, UserTeam, Player
from .serializers import EmailTokenObtainPairSerializer, RegisterSerializer

User = get_user_model()

BASE_BUDGET = Decimal('50000000.00')
MAX_OWNED_PLAYERS = 15

REWARD_BY_RANK = {
    1: Decimal('15000000.00'),
    2: Decimal('10000000.00'),
    3: Decimal('7000000.00'),
    4: Decimal('5000000.00'),
    5: Decimal('3000000.00'),
}
DEFAULT_REWARD = Decimal('2000000.00')


def _player_payload(player):
    return {
        'id': player.player_api_id,
        'name': player.name,
        'position': player.position,
        'team': player.team_name,
        'team_api_id': player.team_api_id,
        'nationality': player.nationality,
        'date_of_birth': player.date_of_birth.isoformat() if player.date_of_birth else None,
        'value': float(player.cost),
    }


def _clean_players(players):
    return [player for player in (players or []) if isinstance(player, dict) and player.get('id') is not None]


def _owned_player_ids(players):
    return {str(player.get('id')) for player in _clean_players(players)}


def _reward_for_rank(rank):
    return REWARD_BY_RANK.get(rank, DEFAULT_REWARD)


def _ensure_team_defaults(team):
    has_owned_players = bool(_clean_players(team.players))
    has_transfers = TransferRecord.objects.filter(user=team.user).exists()
    if not has_owned_players and not has_transfers and team.budget != BASE_BUDGET:
        team.budget = BASE_BUDGET
        team.save(update_fields=['budget'])
    return team


def _normalize_player_from_db(player_obj, existing=None):
    existing = existing or {}
    return {
        'id': player_obj.player_api_id,
        'name': player_obj.name,
        'position': player_obj.position,
        'team': player_obj.team_name,
        'team_api_id': player_obj.team_api_id,
        'value': float(player_obj.cost),
        'added_at': existing.get('added_at') or timezone.now().isoformat(),
    }


def _lineup_for_points(team):
    selected = _clean_players(getattr(team, 'selected_players', None))
    return selected or _clean_players(team.players)


def _squad_payload(*, squad_id, name, selected_players=None, formation='4-4-2', layout=None):
    selected_players = selected_players or []
    return {
        'id': str(squad_id),
        'name': (name or 'Main Squad').strip()[:80],
        'selected_players': selected_players,
        'formation': formation or '4-4-2',
        'layout': layout or {'formation': formation or '4-4-2'},
    }


def _ensure_squads(team):
    squads = list(team.squads or [])
    if not squads:
        active_id = team.active_squad_id or 'default'
        squads = [
            _squad_payload(
                squad_id=active_id,
                name='Main Squad',
                selected_players=team.selected_players or [],
                formation=team.formation,
            )
        ]
        team.squads = squads
        team.active_squad_id = active_id
        team.save(update_fields=['squads', 'active_squad_id'])
        return squads

    active_id = team.active_squad_id or squads[0].get('id') or 'default'
    if not any(str(squad.get('id')) == str(active_id) for squad in squads):
        active_id = squads[0].get('id') or 'default'
        team.active_squad_id = active_id
        team.save(update_fields=['active_squad_id'])
    return squads


def _active_squad(team):
    squads = _ensure_squads(team)
    active_id = team.active_squad_id or squads[0].get('id')
    return next((squad for squad in squads if str(squad.get('id')) == str(active_id)), squads[0])


def _sync_team_from_squad(team, squad):
    team.active_squad_id = str(squad.get('id') or team.active_squad_id or 'default')
    team.selected_players = squad.get('selected_players') or []
    team.formation = squad.get('formation') or '4-4-2'


def _validate_selected_players(players, owned_players):
    owned_ids = _owned_player_ids(owned_players)
    selected_players = []

    for player in players or []:
        if not isinstance(player, dict):
            selected_players.append(None)
            continue
        player_id = player.get('id')
        if player_id is None:
            selected_players.append(None)
            continue
        if str(player_id) not in owned_ids:
            return None, 'Team selection can only include players you have already bought.'

        player_obj = Player.objects.filter(player_api_id=player_id).first()
        if player_obj:
            existing_player = next((owned for owned in owned_players if str(owned.get('id')) == str(player_id)), None)
            selected_players.append(_normalize_player_from_db(player_obj, existing_player))
        else:
            existing_player = next((owned for owned in owned_players if str(owned.get('id')) == str(player_id)), player)
            selected_players.append(existing_player)

    if len(_clean_players(selected_players)) > MAX_OWNED_PLAYERS:
        return None, 'A selected team cannot contain more than 15 players.'

    return selected_players, None


def update_rankings_and_rewards(matchweek=None):
    all_teams = list(UserTeam.objects.all().order_by('-points'))
    for i, team in enumerate(all_teams):
        new_rank = str(i + 1)
        if team.rank != new_rank:
            team.rank = new_rank
            team.save(update_fields=['rank'])

    if matchweek is None:
        matchweeks = []
        for team in all_teams:
            matchweeks.extend(int(key) for key in (team.weekly_points or {}).keys() if str(key).isdigit())
        matchweek = max(matchweeks) if matchweeks else None

    if matchweek is None:
        return

    week_key = str(matchweek)
    eligible_teams = [team for team in all_teams if week_key in (team.weekly_points or {})]
    weekly_rows = sorted(
        eligible_teams,
        key=lambda team: int((team.weekly_points or {}).get(week_key, 0)),
        reverse=True,
    )

    for i, team in enumerate(weekly_rows):
        reward_key = f"mw:{week_key}"
        existing_rewards = list(team.rewards or [])
        if any(item.get('key') == reward_key for item in existing_rewards):
            continue

        reward = _reward_for_rank(i + 1)
        team.budget = Decimal(team.budget) + reward
        existing_rewards.append({
            'key': reward_key,
            'matchweek': matchweek,
            'rank': i + 1,
            'weekly_points': int((team.weekly_points or {}).get(week_key, 0)),
            'reward': float(reward),
            'awarded_at': timezone.now().isoformat(),
        })
        team.rewards = existing_rewards
        team.save(update_fields=['budget', 'rewards'])


def _match_payload(match):
    full_time = (match.get('score') or {}).get('fullTime') or {}
    status_value = match.get('status')
    return {
        'id': match.get('id'),
        'matchday': match.get('matchday'),
        'home_team': match.get('homeTeam', {}).get('shortName') or match.get('homeTeam', {}).get('name'),
        'away_team': match.get('awayTeam', {}).get('shortName') or match.get('awayTeam', {}).get('name'),
        'home_team_id': match.get('homeTeam', {}).get('id'),
        'away_team_id': match.get('awayTeam', {}).get('id'),
        'status': status_value,
        'kickoff': match.get('utcDate'),
        'score': (
            f"{full_time.get('home', '?')} - {full_time.get('away', '?')}"
            if status_value == 'FINISHED'
            else None
        ),
    }


def _difficulty_for_match(match):
    home_id = match.get('homeTeam', {}).get('id') or 0
    away_id = match.get('awayTeam', {}).get('id') or 0
    seed = ((int(home_id) * 7) + (int(away_id) * 11) + int(match.get('matchday') or 0)) % 100
    rating = 1 + (seed % 5)
    return {
        **_match_payload(match),
        'difficulty': rating,
        'difficulty_label': ['Very Easy', 'Easy', 'Moderate', 'Hard', 'Very Hard'][rating - 1],
    }


def _is_attacker_position(position):
    value = (position or '').lower()
    return any(token in value for token in ('offence', 'forward', 'attacker', 'striker', 'winger'))


class GoogleLoginView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        token = request.data.get('credential')
        if not token:
            return Response({'detail': 'Credential is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Specify the CLIENT_ID of the app that accesses the backend:
            # We will use settings to manage the client ID
            client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', None)
            idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), client_id)

            # ID token is valid. Get the user's Google Account ID from the decoded token.
            email = idinfo['email']
            first_name = idinfo.get('given_name', '')
            last_name = idinfo.get('family_name', '')
            username = email.split('@')[0]

            # Find or create user
            user, created = User.objects.get_or_create(email__iexact=email, defaults={
                'email': email,
                'username': username,
                'is_active': True,
                'first_name': first_name,
                'last_name': last_name,
            })

            if created:
                # Random password since they login via Google
                user.set_unusable_password()
                user.save()

            # Create standard JWT tokens
            refresh = RefreshToken.for_user(user)
            return Response({
                'user': {
                    'id': str(user.pk),
                    'username': user.username,
                    'email': user.email,
                    'role': 'admin' if user.is_staff else 'user'
                },
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                },
            })

        except ValueError:
            # Invalid token
            return Response({'detail': 'Invalid Google token.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Catch any other error to prevent HTML responses
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DirectLoginView(APIView):
    """Direct login without 2FA - returns tokens immediately."""
    permission_classes = (AllowAny,)

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        if not email or not password:
            return Response({'detail': 'Email and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(request, username=email, password=password)

        if user is not None:
            refresh = RefreshToken.for_user(user)
            return Response({
                'user': {
                    'id': str(user.pk),
                    'username': user.username,
                    'email': user.email,
                    'role': 'admin' if user.is_staff else 'user'
                },
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                },
            })

        return Response({'detail': 'Invalid email or password.'}, status=status.HTTP_401_UNAUTHORIZED)


class Request2FAView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        if not email or not password:
            return Response({'detail': 'Email and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(request, username=email, password=password)

        if user is not None:
            # Generate tokens immediately
            refresh = RefreshToken.for_user(user)
            return Response({
                'user': {
                    'id': str(user.pk),
                    'username': user.username,
                    'email': user.email,
                    'role': 'admin' if user.is_staff else 'user'
                },
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                },
            })
        
        return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)


class Verify2FAView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        email = request.data.get('email')
        code = request.data.get('code')

        if not email or not code:
            return Response({'detail': 'Email and code are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response({'detail': 'Invalid request.'}, status=status.HTTP_401_UNAUTHORIZED)

        # Check code from AdminProfile if staff, else from User
        is_valid = False
        if user.is_staff:
            try:
                profile = AdminProfile.objects.get(email__iexact=email)
                if profile.two_factor_code == code and profile.two_factor_expiry > timezone.now():
                    is_valid = True
                    profile.two_factor_code = None
                    profile.two_factor_expiry = None
                    profile.save()
            except AdminProfile.DoesNotExist:
                pass
        else:
            if user.two_factor_code == code and user.two_factor_expiry > timezone.now():
                is_valid = True
                user.two_factor_code = None
                user.two_factor_expiry = None
                user.save()

        if is_valid:
            # Generate tokens
            refresh = RefreshToken.for_user(user)
            return Response({
                'user': {
                    'id': str(user.pk),
                    'username': user.username,
                    'email': user.email,
                    'role': 'admin' if user.is_staff else 'user'
                },
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                },
            })
        
        return Response({'detail': 'Invalid or expired code.'}, status=status.HTTP_401_UNAUTHORIZED)


class RequestSignupCodeView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'detail': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if user already exists
        if User.objects.filter(email__iexact=email).exists():
            return Response({'detail': 'A user with this email already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        # Generate 6-digit code
        code = ''.join(random.choices(string.digits, k=6))
        
        # Create a signed token (valid for 10 minutes)
        signup_data = {'email': email, 'code': code, 'timestamp': timezone.now().timestamp()}
        signup_token = signing.dumps(signup_data)

        # Send email
        try:
            send_mail(
                'Your Signup Verification Code',
                f'Your verification code is: {code}. It expires in 10 minutes.',
                settings.EMAIL_HOST_USER,
                [email],
                fail_silently=False,
            )
        except Exception as e:
            print(f"!!! EMAIL FAILED for {email}: {e}")
            # Fallback for visibility
            print(f"\n[SIGNUP CODE FOR {email}]: {code}\n")
        else:
            print(f"### EMAIL SENT SUCCESSFULLY to {email}")

        return Response({
            'detail': 'Verification code sent.',
            'signup_token': signup_token
        })


class RegisterView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        email = request.data.get('email')
        username = request.data.get('username')
        password = request.data.get('password')
        code = request.data.get('code')
        signup_token = request.data.get('signup_token')

        if not all([email, username, password, code, signup_token]):
            return Response({'detail': 'All fields and verification code are required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Verify token
        try:
            data = signing.loads(signup_token, max_age=600) # 10 minute expiry
            if data['email'].lower() != email.lower() or data['code'] != code:
                return Response({'detail': 'Invalid verification code or email mismatch.'}, status=status.HTTP_400_BAD_REQUEST)
        except signing.SignatureExpired:
            return Response({'detail': 'Verification code has expired.'}, status=status.HTTP_400_BAD_REQUEST)
        except signing.BadSignature:
            return Response({'detail': 'Invalid verification token.'}, status=status.HTTP_400_BAD_REQUEST)

        # Proceed with registration
        serializer = RegisterSerializer(data={'email': email, 'username': username, 'password': password})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                'user': {
                    'id': str(user.pk),
                    'username': user.username,
                    'email': user.email,
                    'role': 'user'
                },
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                },
            },
            status=status.HTTP_201_CREATED,
        )


class EmailTokenObtainPairView(TokenObtainPairView):
    permission_classes = (AllowAny,)
    serializer_class = EmailTokenObtainPairSerializer


class AdminStatsView(APIView):
    permission_classes = (IsAdminUser,)

    def get(self, request):
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        admins = User.objects.filter(is_staff=True).count()
        locked_users = User.objects.filter(is_active=False).count()
        return Response(
            {
                'total_users': total_users,
                'active_users': active_users,
                'admins': admins,
                'locked_users': locked_users,
            }
        )


class AdminUsersView(APIView):
    permission_classes = (IsAdminUser,)

    def get(self, request):
        users = User.objects.all().order_by('email')
        return Response(
            [
                {
                    'id': str(user.pk),
                    'email': user.email,
                    'username': user.username,
                    'is_staff': user.is_staff,
                    'is_active': user.is_active,
                }
                for user in users
            ]
        )


class AdminUserDetailView(APIView):
    permission_classes = (IsAdminUser,)

    def patch(self, request, user_id):
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        for field in ('is_staff', 'is_active'):
            if field in request.data:
                setattr(user, field, bool(request.data.get(field)))

        user.save()

        return Response(
            {
                'id': str(user.pk),
                'email': user.email,
                'username': user.username,
                'is_staff': user.is_staff,
                'is_active': user.is_active,
            }
        )


class AdminPlayersView(APIView):
    permission_classes = (IsAdminUser,)

    def get(self, request):
        players = Player.objects.all().order_by('team_name', 'name')
        return Response([_player_payload(player) for player in players])

    def post(self, request):
        required = ['name', 'position']
        missing = [field for field in required if not request.data.get(field)]
        if missing:
            return Response(
                {'detail': f"Missing required fields: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        player_api_id = request.data.get('player_api_id')
        if player_api_id is None:
            last_player = Player.objects.order_by('-player_api_id').first()
            player_api_id = (last_player.player_api_id + 1) if last_player else 1

        player, created = Player.objects.update_or_create(
            player_api_id=int(player_api_id),
            defaults={
                'name': request.data.get('name'),
                'position': request.data.get('position'),
                'nationality': request.data.get('nationality', ''),
                'team_name': request.data.get('team_name') or request.data.get('team', ''),
                'team_api_id': request.data.get('team_api_id') or None,
                'cost': Decimal(str(request.data.get('cost') or request.data.get('value') or '5000000.00')),
            },
        )
        return Response(_player_payload(player), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class AdminPlayerDetailView(APIView):
    permission_classes = (IsAdminUser,)

    def patch(self, request, player_id):
        player = Player.objects.filter(player_api_id=player_id).first()
        if not player:
            return Response({'detail': 'Player not found.'}, status=status.HTTP_404_NOT_FOUND)

        field_map = {
            'name': 'name',
            'position': 'position',
            'team': 'team_name',
            'team_name': 'team_name',
            'team_api_id': 'team_api_id',
            'nationality': 'nationality',
        }
        for incoming, model_field in field_map.items():
            if incoming in request.data:
                setattr(player, model_field, request.data.get(incoming))
        if 'cost' in request.data or 'value' in request.data:
            player.cost = Decimal(str(request.data.get('cost') or request.data.get('value')))
        player.save()
        return Response(_player_payload(player))

    def delete(self, request, player_id):
        deleted, _ = Player.objects.filter(player_api_id=player_id).delete()
        if not deleted:
            return Response({'detail': 'Player not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminMatchesView(APIView):
    permission_classes = (IsAdminUser,)

    def get(self, request):
        requested_status = request.query_params.get('status')
        matches = fetch_pl_matches(limit=None, status=requested_status)
        return Response([_match_payload(match) for match in matches])


class UserDashboardView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        print(f"DEBUG: UserDashboardView.get called for user: {request.user}")
        try:
            team = UserTeam.objects.filter(user=request.user).first()
            print(f"DEBUG: Team found: {team}")
            if not team:
                print(f"DEBUG: Creating new team for user: {request.user}")
                team = UserTeam.objects.create(user=request.user, budget=BASE_BUDGET)
            team = _ensure_team_defaults(team)
            
            # Basic consistency check: reset budget if empty team has 0 budget
            current_budget = float(team.budget)
            print(f"DEBUG: Current budget: {current_budget}")
            if current_budget == 0 and not _clean_players(team.players):
                team.budget = BASE_BUDGET
                team.save()
                
            return Response(
                {
                    'points': team.points,
                    'rank': team.rank,
                    'transfers_left': team.free_transfers,
                    'budget': float(team.budget),
                    'team_size': len(_lineup_for_points(team)),
                    'owned_count': len(_clean_players(team.players)),
                    'watchlist_count': len(team.watchlist or []),
                    'rewards': team.rewards or [],
                    'last_synced_at': team.last_synced_at.isoformat() if team.last_synced_at else None,
                    'points_history': [
                        {'week': f"MW {week}", 'points': int((team.weekly_points or {}).get(str(week), 0))}
                        for week in sorted([int(key) for key in (team.weekly_points or {}).keys() if str(key).isdigit()])[-6:]
                    ],
                }
            )
        except Exception as e:
            import traceback
            trace = traceback.format_exc()
            print(f"ERROR in UserDashboardView: {e}")
            print(trace)
            return Response({'detail': f"Backend Error: {str(e)}", 'traceback': trace[:500]}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserTeamView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        team, _ = UserTeam.objects.get_or_create(user=request.user)
        team = _ensure_team_defaults(team)
        
        # Trigger automatic point sync on dashboard load
        sync_user_points(request.user)
        # Reload team after sync
        team.refresh_from_db()
        owned_players = _clean_players(team.players)
        active_squad = _active_squad(team)
        _sync_team_from_squad(team, active_squad)
        team.save(update_fields=['selected_players', 'formation', 'active_squad_id'])
        selected_players = active_squad.get('selected_players') or []
        
        return Response({
            'budget': float(team.budget),
            'formation': team.formation,
            'squad_id': team.active_squad_id,
            'squad_name': active_squad.get('name', 'Main Squad'),
            'active_squad_id': team.active_squad_id,
            'squads': team.squads or [],
            'players': selected_players,
            'selected_players': selected_players,
            'owned_players': owned_players,
            'owned_count': len(owned_players),
            'max_players': MAX_OWNED_PLAYERS,
            'points': team.points,
            'rank': team.rank,
            'transfers_left': team.free_transfers,
            'rewards': team.rewards or [],
        })
        
    def post(self, request):
        team, _ = UserTeam.objects.get_or_create(user=request.user)
        team = _ensure_team_defaults(team)
        squads = _ensure_squads(team)
        action = request.data.get('action', 'update_squad')
        requested_squad_id = request.data.get('squad_id') or team.active_squad_id
        players = request.data.get('players', [])
        formation = request.data.get('formation', '4-4-2')
        owned_players = _clean_players(team.players)

        if action == 'create_squad':
            squad_name = (request.data.get('squad_name') or request.data.get('name') or f"Squad {len(squads) + 1}").strip()
            new_squad = _squad_payload(
                squad_id=uuid.uuid4().hex,
                name=squad_name,
                selected_players=[],
                formation=formation or team.formation,
            )
            squads.append(new_squad)
            team.squads = squads
            _sync_team_from_squad(team, new_squad)
            team.save(update_fields=['squads', 'selected_players', 'formation', 'active_squad_id'])
        elif action == 'switch_squad':
            squad = next((item for item in squads if str(item.get('id')) == str(requested_squad_id)), None)
            if not squad:
                return Response({'detail': 'Squad not found.'}, status=status.HTTP_404_NOT_FOUND)
            _sync_team_from_squad(team, squad)
            team.save(update_fields=['selected_players', 'formation', 'active_squad_id'])
        else:
            squad = next((item for item in squads if str(item.get('id')) == str(requested_squad_id)), None)
            if not squad:
                return Response({'detail': 'Squad not found.'}, status=status.HTTP_404_NOT_FOUND)

            selected_players, error = _validate_selected_players(players, owned_players)
            if error:
                return Response(
                    {'detail': error},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            squad['selected_players'] = selected_players
            squad['formation'] = formation
            squad['layout'] = {'formation': formation}
            if 'squad_name' in request.data or 'name' in request.data:
                squad['name'] = (request.data.get('squad_name') or request.data.get('name') or squad.get('name') or 'Squad').strip()[:80]

            team.squads = squads
            _sync_team_from_squad(team, squad)
            team.save(update_fields=['squads', 'selected_players', 'formation', 'active_squad_id'])

        active_squad = _active_squad(team)
        return Response({
            'budget': float(team.budget),
            'formation': team.formation,
            'squad_id': team.active_squad_id,
            'squad_name': active_squad.get('name', 'Main Squad'),
            'active_squad_id': team.active_squad_id,
            'squads': team.squads or [],
            'players': team.selected_players or [],
            'selected_players': team.selected_players or [],
            'owned_players': owned_players,
            'owned_count': len(owned_players),
            'max_players': MAX_OWNED_PLAYERS,
            'points': team.points,
        })


class UserMatchesView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        matches = fetch_pl_matches(limit=None)
        requested_status = request.query_params.get('status')
        if requested_status:
            allowed = {value.strip().upper() for value in requested_status.split(',') if value.strip()}
            matches = [match for match in matches if match.get('status') in allowed]

        payload = [_match_payload(match) for match in matches]
        payload.sort(key=lambda item: (item.get('matchday') or 99, item.get('kickoff') or ''))
        return Response(payload)


class LiveScoresView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        live_statuses = {'LIVE', 'IN_PLAY', 'PAUSED'}
        matches = fetch_pl_matches(limit=None)
        live_matches = [match for match in matches if match.get('status') in live_statuses]
        return Response([_match_payload(match) for match in live_matches])


class MatchDifficultyView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        matches = fetch_pl_matches(limit=None)
        upcoming = [match for match in matches if match.get('status') in {'SCHEDULED', 'TIMED'}]
        return Response([_difficulty_for_match(match) for match in upcoming[:20]])


class TopAttackersView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        scorers = fetch_pl_scorers(limit=30)
        rows = []

        for scorer in scorers:
            player_data = scorer.get('player') or {}
            player_id = player_data.get('id')
            player_name = player_data.get('name')
            goals = scorer.get('goals') or scorer.get('numberOfGoals') or 0
            local_player = None
            if player_id is not None:
                local_player = Player.objects.filter(player_api_id=player_id).first()
            if not local_player and player_name:
                local_player = Player.objects.filter(name__iexact=player_name).first()

            if local_player and not _is_attacker_position(local_player.position):
                continue
            if not player_name and local_player:
                player_name = local_player.name

            if player_name:
                rows.append({'name': player_name, 'goals': int(goals)})
            if len(rows) == 5:
                break

        if len(rows) < 5:
            fallback_players = Player.objects.filter(position__in=['Offence', 'Forward', 'Attacker']).order_by('name')[: 5 - len(rows)]
            used_names = {row['name'] for row in rows}
            for index, player in enumerate(fallback_players):
                if player.name in used_names:
                    continue
                rows.append({'name': player.name, 'goals': max(0, 5 - index)})
                if len(rows) == 5:
                    break

        if not rows:
            rows = [
                {'name': 'Erling Haaland', 'goals': 18},
                {'name': 'Mohamed Salah', 'goals': 16},
                {'name': 'Alexander Isak', 'goals': 14},
                {'name': 'Ollie Watkins', 'goals': 12},
                {'name': 'Bukayo Saka', 'goals': 10},
            ]

        return Response(rows[:5])


class UserTransferMarketView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        team, _ = UserTeam.objects.get_or_create(user=request.user)
        team = _ensure_team_defaults(team)
        owned_ids = _owned_player_ids(team.players)
        players = Player.objects.all()
        market = []
        for p in players:
            market.append({
                'id': p.player_api_id,
                'name': p.name,
                'position': p.position,
                'team': p.team_name,
                'value': float(p.cost),
                'is_owned': str(p.player_api_id) in owned_ids,
            })
        return Response(market)


class UserTransferSubmitView(APIView):
    permission_classes = (IsAuthenticated,)

    def _get_official_cost(self, player_id, fallback_value):
        """Get the official player cost from DB, with a fallback to the stored value."""
        try:
            p = Player.objects.filter(player_api_id=int(player_id)).first()
            if p:
                return Decimal(p.cost)
        except (ValueError, TypeError, Exception):
            pass
        try:
            return Decimal(str(fallback_value or 0))
        except Exception:
            return Decimal('0.00')

    @transaction.atomic
    def post(self, request):
        mode = request.data.get('mode', 'swap')  # 'buy', 'sell', or 'swap'
        out_name = request.data.get('outName')
        out_id = request.data.get('outId')
        in_name = request.data.get('inName')
        player_in_data = request.data.get('playerIn')

        team, _ = UserTeam.objects.get_or_create(user=request.user)
        team = _ensure_team_defaults(team)
        squads = _ensure_squads(team)
        players = _clean_players(team.players)
        selected_players = list(team.selected_players or [])
        players_by_name = {p.get('name'): p for p in players if p is not None}
        players_by_id = {str(p.get('id')): p for p in players if p is not None}
        current_budget = Decimal(team.budget)

        print(f"[Transfer] mode={mode} out={out_name} in={in_name} budget={current_budget}")

        if mode == 'sell':
            if not out_name and out_id is None:
                return Response({'detail': 'A player is required for sell.'}, status=status.HTTP_400_BAD_REQUEST)
            player_out = players_by_id.get(str(out_id)) if out_id is not None else players_by_name.get(out_name)
            if not player_out:
                return Response({'detail': f'"{out_name or out_id}" is not in your owned players.'}, status=status.HTTP_400_BAD_REQUEST)

            sell_value = self._get_official_cost(player_out.get('id'), player_out.get('value', 0))
            print(f"[Transfer] Selling {out_name} refund={sell_value}")
            current_budget += sell_value
            players = [p for p in players if str(p.get('id')) != str(player_out.get('id'))]
            selected_players = [
                None if isinstance(p, dict) and str(p.get('id')) == str(player_out.get('id')) else p
                for p in selected_players
            ]
            for squad in squads:
                squad['selected_players'] = [
                    None if isinstance(p, dict) and str(p.get('id')) == str(player_out.get('id')) else p
                    for p in (squad.get('selected_players') or [])
                ]
            TransferRecord.objects.create(user=request.user, player_out=player_out.get('name', out_name), player_in='(sold)')

        elif mode == 'buy':
            if not in_name or not isinstance(player_in_data, dict):
                return Response({'detail': 'inName and playerIn are required for buy.'}, status=status.HTTP_400_BAD_REQUEST)

            player_in_id = player_in_data.get('id')
            if player_in_id is None:
                return Response({'detail': 'Player id is required for buy.'}, status=status.HTTP_400_BAD_REQUEST)
            if len(players) >= MAX_OWNED_PLAYERS:
                return Response({'detail': 'You can only own a maximum of 15 players.'}, status=status.HTTP_400_BAD_REQUEST)
            if str(player_in_id) in players_by_id:
                return Response({'detail': f'"{in_name}" is already owned.'}, status=status.HTTP_400_BAD_REQUEST)

            buy_cost = self._get_official_cost(player_in_data.get('id'), player_in_data.get('value', 0))
            print(f"[Transfer] Buying {in_name} cost={buy_cost} budget={current_budget}")

            if current_budget < buy_cost:
                return Response(
                    {'detail': 'Insufficient funds'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            current_budget -= buy_cost
            player_obj = Player.objects.filter(player_api_id=player_in_id).first()
            new_player = {
                'id': player_in_id,
                'name': player_obj.name if player_obj else in_name,
                'position': player_obj.position if player_obj else player_in_data.get('position', 'FWD'),
                'team': player_obj.team_name if player_obj else player_in_data.get('team', ''),
                'team_api_id': player_obj.team_api_id if player_obj else player_in_data.get('team_api_id'),
                'value': float(buy_cost),
                'added_at': timezone.now().isoformat(),
            }
            players.append(new_player)
            TransferRecord.objects.create(user=request.user, player_out='(bought)', player_in=new_player['name'])

        elif mode == 'swap':
            if not out_name or not in_name or not isinstance(player_in_data, dict):
                return Response({'detail': 'outName, inName, and playerIn are required for swap.'}, status=status.HTTP_400_BAD_REQUEST)
            player_in_id = player_in_data.get('id')
            if str(player_in_id) in players_by_id:
                return Response({'detail': f'"{in_name}" is already owned.'}, status=status.HTTP_400_BAD_REQUEST)
            if out_name not in players_by_name:
                return Response({'detail': f'"{out_name}" is not in your team.'}, status=status.HTTP_400_BAD_REQUEST)

            player_out = players_by_name[out_name]
            sell_value = self._get_official_cost(player_out.get('id'), player_out.get('value', 0))
            buy_cost = self._get_official_cost(player_in_data.get('id'), player_in_data.get('value', 0))
            net = sell_value - buy_cost
            print(f"[Transfer] Swap sell={sell_value} buy={buy_cost} net={net}")

            if current_budget + net < 0:
                return Response(
                    {'detail': 'Insufficient funds'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            current_budget += net
            player_obj = Player.objects.filter(player_api_id=player_in_id).first()
            new_player = {
                'id': player_in_id,
                'name': player_obj.name if player_obj else in_name,
                'position': player_obj.position if player_obj else player_in_data.get('position', 'FWD'),
                'team': player_obj.team_name if player_obj else player_in_data.get('team', ''),
                'team_api_id': player_obj.team_api_id if player_obj else player_in_data.get('team_api_id'),
                'value': float(buy_cost),
                'added_at': timezone.now().isoformat(),
            }
            # Replace in slot
            for i, p in enumerate(players):
                if p and p.get('name') == out_name:
                    players[i] = new_player
                    break
            selected_players = [
                new_player if isinstance(p, dict) and p.get('name') == out_name else p
                for p in selected_players
            ]
            for squad in squads:
                squad['selected_players'] = [
                    new_player if isinstance(p, dict) and p.get('name') == out_name else p
                    for p in (squad.get('selected_players') or [])
                ]
            TransferRecord.objects.create(user=request.user, player_out=out_name, player_in=in_name)

        else:
            return Response({'detail': f'Unknown mode: {mode}'}, status=status.HTTP_400_BAD_REQUEST)

        team.players = players
        team.budget = current_budget
        team.selected_players = selected_players
        team.squads = squads
        team.save(update_fields=['players', 'selected_players', 'squads', 'budget'])
        print(f"[Transfer] Done. budget={current_budget} players={len(team.players)}")

        return Response({
            'message': 'Transfer completed successfully.',
            'budget': float(team.budget),
            'team': team.players,
            'owned_players': team.players,
            'selected_players': team.selected_players,
            'owned_count': len(_clean_players(team.players)),
            'max_players': MAX_OWNED_PLAYERS,
        })


class TransferHistoryView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        records = TransferRecord.objects.filter(user=request.user).order_by('-created_at')[:50]
        return Response([
            {
                'id': str(record.pk),
                'player_out': record.player_out,
                'player_in': record.player_in,
                'created_at': record.created_at.isoformat(),
            }
            for record in records
        ])


class WatchlistView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        team, _ = UserTeam.objects.get_or_create(user=request.user)
        return Response(team.watchlist or [])

    def post(self, request):
        player_id = request.data.get('id')
        if player_id is None:
            return Response({'detail': 'Player id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        team, _ = UserTeam.objects.get_or_create(user=request.user)
        watchlist = list(team.watchlist or [])
        player = Player.objects.filter(player_api_id=player_id).first()
        payload = _player_payload(player) if player else {
            'id': player_id,
            'name': request.data.get('name', 'Unknown player'),
            'position': request.data.get('position', ''),
            'team': request.data.get('team', ''),
            'value': request.data.get('value', 0),
        }

        if not any(str(item.get('id')) == str(player_id) for item in watchlist):
            watchlist.append(payload)
            team.watchlist = watchlist
            team.save(update_fields=['watchlist'])
        return Response(team.watchlist)

    def delete(self, request):
        player_id = request.data.get('id') or request.query_params.get('id')
        if player_id is None:
            return Response({'detail': 'Player id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        team, _ = UserTeam.objects.get_or_create(user=request.user)
        team.watchlist = [item for item in (team.watchlist or []) if str(item.get('id')) != str(player_id)]
        team.save(update_fields=['watchlist'])
        return Response(team.watchlist)


class NotificationsView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        team, _ = UserTeam.objects.get_or_create(user=request.user)
        notifications = list(team.notifications or [])
        if not notifications:
            notifications = [
                {
                    'id': 'welcome',
                    'type': 'info',
                    'message': 'Build your squad and sync points after completed matchweeks.',
                    'created_at': timezone.now().isoformat(),
                    'read': False,
                }
            ]
        return Response(notifications)

    def post(self, request):
        team, _ = UserTeam.objects.get_or_create(user=request.user)
        notifications = list(team.notifications or [])
        notifications.append({
            'id': request.data.get('id') or f"alert-{timezone.now().timestamp()}",
            'type': request.data.get('type', 'info'),
            'message': request.data.get('message', 'New alert'),
            'created_at': timezone.now().isoformat(),
            'read': bool(request.data.get('read', False)),
        })
        team.notifications = notifications[-25:]
        team.save(update_fields=['notifications'])
        return Response(team.notifications)


class AnalyticsSummaryView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        team, _ = UserTeam.objects.get_or_create(user=request.user)
        team = _ensure_team_defaults(team)
        squad = _lineup_for_points(team)
        owned = _clean_players(team.players)
        by_position = {}
        for player in squad:
            position = player.get('position') or 'Unknown'
            by_position[position] = by_position.get(position, 0) + 1

        return Response({
            'points': team.points,
            'rank': team.rank,
            'budget': float(team.budget),
            'team_size': len(squad),
            'owned_count': len(owned),
            'watchlist_count': len(team.watchlist or []),
            'rewards': team.rewards or [],
            'position_breakdown': by_position,
            'points_history': [
                {'week': f"MW {week}", 'points': int((team.weekly_points or {}).get(str(week), 0))}
                for week in sorted([int(key) for key in (team.weekly_points or {}).keys() if str(key).isdigit()])[-6:]
            ],
        })


class ProfileUpdateView(APIView):
    permission_classes = (IsAuthenticated,)

    def patch(self, request):
        user = request.user
        username = request.data.get('username')
        email = request.data.get('email')

        if username:
            user.username = username
        if email:
            if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                return Response({'detail': 'Email already in use.'}, status=status.HTTP_400_BAD_REQUEST)
            user.email = email.lower()
        
        user.save()
        return Response({
            'user': {
                'id': str(user.pk),
                'username': user.username,
                'email': user.email,
                'role': 'admin' if user.is_staff else 'user'
            }
        })

class ChangePasswordView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user = request.user
        current_password = request.data.get('currentPassword')
        new_password = request.data.get('newPassword')

        if not current_password or not new_password:
            return Response({'detail': 'Both current and new passwords are required.'}, status=status.HTTP_400_BAD_REQUEST)

        if not user.check_password(current_password):
            return Response({'detail': 'Incorrect current password.'}, status=status.HTTP_400_BAD_REQUEST)

        if len(new_password) < 8:
            return Response({'detail': 'New password must be at least 8 characters.'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()
        return Response({'detail': 'Password updated successfully.'})


class PasswordResetRequestView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
        if not email:
            return Response({'detail': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(email__iexact=email, is_active=True).first()
        reset_token = None
        if user:
            reset_token = signing.dumps({'user_id': str(user.pk), 'email': user.email})
            try:
                send_mail(
                    'Fantasy Football password reset',
                    (
                        'Use this password reset token in the app. '
                        f'This token expires in 30 minutes: {reset_token}'
                    ),
                    settings.EMAIL_HOST_USER,
                    [user.email],
                    fail_silently=False,
                )
            except Exception as e:
                print(f"!!! PASSWORD RESET EMAIL FAILED for {email}: {e}")
                print(f"\n[PASSWORD RESET TOKEN FOR {email}]: {reset_token}\n")

        payload = {'detail': 'If an account exists for that email, a reset token has been sent.'}
        if settings.DEBUG and reset_token:
            payload['reset_token'] = reset_token
        return Response(payload)


class PasswordResetConfirmView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        token = request.data.get('token')
        new_password = request.data.get('newPassword') or request.data.get('new_password')

        if not token or not new_password:
            return Response({'detail': 'Token and new password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            data = signing.loads(token, max_age=1800)
            user = User.objects.get(pk=data.get('user_id'), email__iexact=data.get('email'), is_active=True)
            validate_password(new_password, user=user)
        except signing.SignatureExpired:
            return Response({'detail': 'Password reset token has expired.'}, status=status.HTTP_400_BAD_REQUEST)
        except (signing.BadSignature, User.DoesNotExist):
            return Response({'detail': 'Invalid password reset token.'}, status=status.HTTP_400_BAD_REQUEST)
        except ValidationError as e:
            return Response({'detail': ' '.join(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()
        return Response({'detail': 'Password reset successfully. You can now log in.'})


class LeaderboardView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        try:
            update_rankings_and_rewards()
            teams = UserTeam.objects.all().order_by('-points')
            leaderboard = []
            for i, team in enumerate(teams):
                rank = i + 1
                leaderboard.append({
                    'rank': rank,
                    'username': team.user.username,
                    'points': team.points,
                    'reward': float(_reward_for_rank(rank)),
                    'budget': float(team.budget),
                    'rewards': team.rewards or [],
                    'is_me': team.user == request.user
                })
            return Response(leaderboard)
        except Exception as e:
            import traceback
            print(f"ERROR in LeaderboardView: {e}")
            print(traceback.format_exc())
            return Response({'detail': f"Backend Error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class WeeklyLeaderboardView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        try:
            matchweek = request.query_params.get('matchweek')
            if matchweek is None:
                weeks = []
                for team in UserTeam.objects.all():
                    weeks.extend(int(key) for key in (team.weekly_points or {}).keys() if str(key).isdigit())
                matchweek = max(weeks) if weeks else None
            else:
                matchweek = int(matchweek)

            if matchweek is not None:
                update_rankings_and_rewards(matchweek=matchweek)

            week_key = str(matchweek) if matchweek is not None else None
            teams = list(UserTeam.objects.all())
            teams.sort(key=lambda team: int((team.weekly_points or {}).get(week_key, 0)) if week_key else 0, reverse=True)

            rows = []
            for i, team in enumerate(teams):
                rank = i + 1
                weekly_points = int((team.weekly_points or {}).get(week_key, 0)) if week_key else 0
                rows.append({
                    'rank': rank,
                    'matchweek': matchweek,
                    'username': team.user.username,
                    'points': weekly_points,
                    'weekly_points': weekly_points,
                    'reward': float(_reward_for_rank(rank)),
                    'budget': float(team.budget),
                    'is_me': team.user == request.user,
                })
            return Response(rows)
        except Exception as e:
            import traceback
            print(f"ERROR in WeeklyLeaderboardView: {e}")
            print(traceback.format_exc())
            return Response({'detail': f"Backend Error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def sync_user_points(user, initial=False):
    """
    Core logic to sync points for a user based on finished matches.
    If initial=True, it will process the last 2 finished matchdays regardless of processed_matchweeks.
    """
    try:
        team, _ = UserTeam.objects.get_or_create(user=user)
        # Fetch a large set of finished matches
        finished_matches = fetch_pl_matches(limit=500, status='FINISHED')
        if not finished_matches:
            return 0
        
        # Group matches by matchday
        matches_by_day = {}
        for m in finished_matches:
            day = m.get('matchday')
            if day:
                if day not in matches_by_day:
                    matches_by_day[day] = []
                matches_by_day[day].append(m)
        
        finished_days = sorted(matches_by_day.keys(), reverse=True)
        if not finished_days:
            return 0

        processed = set(team.processed_matchweeks or [])
        new_points = 0
        days_to_process = []

        if initial or not processed:
            # For initial sync, we take the last 2 finished matchdays as a starting point
            days_to_process = finished_days[:2]
            # Clear processed for the days we are about to add to ensure no double counting if called again
            processed = set([d for d in processed if d not in days_to_process])
        else:
            # Find all matchdays that haven't been processed yet
            for d in finished_days:
                if d not in processed:
                    days_to_process.append(d)

        if not days_to_process:
            return 0

        players = _lineup_for_points(team)
        weekly_points = dict(team.weekly_points or {})
        for day in days_to_process:
            day_matches = matches_by_day[day]
            day_points = 0
            
            # Map team_id to result for this day
            results = {} # team_id -> points (3 for win, 1 for draw)
            for m in day_matches:
                home_team = m.get('homeTeam', {})
                away_team = m.get('awayTeam', {})
                ht = home_team.get('id')
                at = away_team.get('id')
                score = m.get('score', {}).get('fullTime', {})
                hs = score.get('home')
                ascore = score.get('away')
                
                if ht and at and hs is not None and ascore is not None:
                    if hs > ascore:
                        results[ht] = 3
                        results[at] = 0
                    elif ascore > hs:
                        results[at] = 3
                        results[ht] = 0
                    else:
                        results[ht] = 1
                        results[at] = 1
            
            # Calculate points for squad
            for p in players:
                if not isinstance(p, dict):
                    continue
                player_id = p.get('id')
                player_obj = Player.objects.filter(player_api_id=player_id).first()
                if player_obj and player_obj.team_api_id in results:
                    day_points += results[player_obj.team_api_id]
            
            weekly_points[str(day)] = int(weekly_points.get(str(day), 0)) + int(day_points)
            new_points += day_points
            processed.add(day)

        team.points += new_points
        team.weekly_points = weekly_points
        team.processed_matchweeks = sorted(list(processed))
        team.last_synced_at = timezone.now()
        team.save()

        update_rankings_and_rewards(matchweek=max(days_to_process) if days_to_process else None)
            
        return new_points
    except Exception as e:
        print(f"Error syncing points for {user.email}: {e}")
        return 0


class SyncPointsView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        initial = request.data.get('initial', False)
        new_points = sync_user_points(request.user, initial=initial)
        
        team = UserTeam.objects.get(user=request.user)
        return Response({
            'detail': 'Points synchronized successfully.',
            'new_points': new_points,
            'total_points': team.points,
            'processed_matchweeks': team.processed_matchweeks,
            'weekly_points': team.weekly_points,
            'budget': float(team.budget),
            'rewards': team.rewards or [],
        })
