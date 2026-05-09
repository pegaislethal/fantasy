from datetime import timedelta
import random
import string

from django.contrib.auth import get_user_model, authenticate
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


class UserDashboardView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        print(f"DEBUG: UserDashboardView.get called for user: {request.user}")
        try:
            team = UserTeam.objects.filter(user=request.user).first()
            print(f"DEBUG: Team found: {team}")
            if not team:
                print(f"DEBUG: Creating new team for user: {request.user}")
                team = UserTeam.objects.create(user=request.user, budget=100000000.00)
            
            # Basic consistency check: reset budget if empty team has 0 budget
            current_budget = float(team.budget)
            print(f"DEBUG: Current budget: {current_budget}")
            if current_budget == 0 and (not team.players or len(team.players) == 0):
                team.budget = 100000000.00
                team.save()
                
            return Response(
                {
                    'points': team.points,
                    'rank': team.rank,
                    'transfers_left': team.free_transfers,
                    'budget': float(team.budget),
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
        
        # Trigger automatic point sync on dashboard load
        sync_user_points(request.user)
        # Reload team after sync
        team.refresh_from_db()
        
        return Response({
            'budget': float(team.budget),
            'formation': team.formation,
            'players': team.players or [],
            'points': team.points,
            'rank': team.rank,
        })
        
    def post(self, request):
        team, _ = UserTeam.objects.get_or_create(user=request.user)
        players = request.data.get('players', [])
        formation = request.data.get('formation', '4-4-2')
        
        # Calculate total cost of submitted players
        total_cost = 0
        for p in players:
            if not isinstance(p, dict):
                continue
            player_obj = Player.objects.filter(player_api_id=p.get('id')).first()
            if player_obj:
                total_cost += float(player_obj.cost)
                p['value'] = float(player_obj.cost)
                p['name'] = player_obj.name
                p['position'] = player_obj.position
                p['team'] = player_obj.team_name
                # Keep existing added_at if present, otherwise set now
                existing_player = next((ep for ep in (team.players or []) if ep.get('id') == p.get('id')), None)
                p['added_at'] = existing_player.get('added_at') if existing_player and existing_player.get('added_at') else timezone.now().isoformat()
                
        # Starting budget is 100M
        remaining_budget = 100000000.00 - float(total_cost)
        if remaining_budget < 0:
            return Response({'detail': 'Over budget!'}, status=status.HTTP_400_BAD_REQUEST)
            
        team.players = players
        team.formation = formation
        team.budget = remaining_budget
        team.save()
        return Response({
            'budget': float(team.budget),
            'formation': team.formation,
            'players': team.players or [],
            'points': team.points,
        })


class UserMatchesView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        # Fetch a larger set of finished matches and take the last 10 (most recent)
        finished_raw = fetch_pl_matches(limit=100, status='FINISHED')
        # Take the tail of finished matches if any, these are the latest
        finished = finished_raw[-10:] if finished_raw else []
        
        # Fetch upcoming
        scheduled = fetch_pl_matches(limit=20, status='SCHEDULED')
        matches = finished + scheduled
        
        payload = []
        for match in matches:
            payload.append(
                {
                    'id': match.get('id'),
                    'home_team': match.get('homeTeam', {}).get('shortName') or match.get('homeTeam', {}).get('name'),
                    'away_team': match.get('awayTeam', {}).get('shortName') or match.get('awayTeam', {}).get('name'),
                    'status': match.get('status'),
                    'kickoff': match.get('utcDate'),
                    'score': f"{match.get('score', {}).get('fullTime', {}).get('home', '?')} - {match.get('score', {}).get('fullTime', {}).get('away', '?')}" if match.get('status') == 'FINISHED' else None
                }
            )
        return Response(payload)


class UserTransferMarketView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        players = Player.objects.all()
        market = []
        for p in players:
            market.append({
                'id': p.player_api_id,
                'name': p.name,
                'position': p.position,
                'team': p.team_name,
                'value': p.cost,
            })
        return Response(market)


class UserTransferSubmitView(APIView):
    permission_classes = (IsAuthenticated,)

    def _get_official_cost(self, player_id, fallback_value):
        """Get the official player cost from DB, with a fallback to the stored value."""
        try:
            p = Player.objects.filter(player_api_id=int(player_id)).first()
            if p:
                return float(p.cost)
        except (ValueError, TypeError, Exception):
            pass
        try:
            return float(fallback_value or 0)
        except (ValueError, TypeError):
            return 0.0

    @transaction.atomic
    def post(self, request):
        mode = request.data.get('mode', 'swap')  # 'buy', 'sell', or 'swap'
        out_name = request.data.get('outName')
        in_name = request.data.get('inName')
        player_in_data = request.data.get('playerIn')

        team, _ = UserTeam.objects.get_or_create(user=request.user)
        players = list(team.players or [])
        players_by_name = {p.get('name'): p for p in players if p is not None}
        current_budget = float(team.budget)

        print(f"[Transfer] mode={mode} out={out_name} in={in_name} budget={current_budget}")

        if mode == 'sell':
            if not out_name:
                return Response({'detail': 'outName is required for sell.'}, status=status.HTTP_400_BAD_REQUEST)
            if out_name not in players_by_name:
                return Response({'detail': f'"{out_name}" is not in your team.'}, status=status.HTTP_400_BAD_REQUEST)

            player_out = players_by_name[out_name]
            sell_value = self._get_official_cost(player_out.get('id'), player_out.get('value', 0))
            print(f"[Transfer] Selling {out_name} refund={sell_value}")
            current_budget += sell_value
            
            # Remove from list while preserving indices
            for i, p in enumerate(players):
                if p and p.get('name') == out_name:
                    players[i] = None
                    break
            TransferRecord.objects.create(user=request.user, player_out=out_name, player_in='(sold)')

        elif mode == 'buy':
            if not in_name or not isinstance(player_in_data, dict):
                return Response({'detail': 'inName and playerIn are required for buy.'}, status=status.HTTP_400_BAD_REQUEST)

            buy_cost = self._get_official_cost(player_in_data.get('id'), player_in_data.get('value', 0))
            print(f"[Transfer] Buying {in_name} cost={buy_cost} budget={current_budget}")

            if current_budget < buy_cost:
                return Response(
                    {'detail': f'Insufficient budget. Cost: \xa3{buy_cost/1e6:.1f}M, Available: \xa3{current_budget/1e6:.1f}M.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            current_budget -= buy_cost
            new_player = {
                'id': player_in_data.get('id'),
                'name': in_name,
                'position': player_in_data.get('position', 'FWD'),
                'team': player_in_data.get('team', ''),
                'value': str(buy_cost),
                'added_at': timezone.now().isoformat(),
            }
            # Find first empty slot or append
            slot_found = False
            for i, p in enumerate(players):
                if p is None:
                    players[i] = new_player
                    slot_found = True
                    break
            if not slot_found:
                players.append(new_player)
            TransferRecord.objects.create(user=request.user, player_out='(bought)', player_in=in_name)

        elif mode == 'swap':
            if not out_name or not in_name or not isinstance(player_in_data, dict):
                return Response({'detail': 'outName, inName, and playerIn are required for swap.'}, status=status.HTTP_400_BAD_REQUEST)
            if out_name not in players_by_name:
                return Response({'detail': f'"{out_name}" is not in your team.'}, status=status.HTTP_400_BAD_REQUEST)

            player_out = players_by_name[out_name]
            sell_value = self._get_official_cost(player_out.get('id'), player_out.get('value', 0))
            buy_cost = self._get_official_cost(player_in_data.get('id'), player_in_data.get('value', 0))
            net = sell_value - buy_cost
            print(f"[Transfer] Swap sell={sell_value} buy={buy_cost} net={net}")

            if current_budget + net < 0:
                return Response(
                    {'detail': f'Insufficient budget for swap. Need \xa3{abs(net)/1e6:.1f}M more.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            current_budget += net
            new_player = {
                'id': player_in_data.get('id'),
                'name': in_name,
                'position': player_in_data.get('position', 'FWD'),
                'team': player_in_data.get('team', ''),
                'value': str(buy_cost),
                'added_at': timezone.now().isoformat(),
            }
            # Replace in slot
            for i, p in enumerate(players):
                if p and p.get('name') == out_name:
                    players[i] = new_player
                    break
            TransferRecord.objects.create(user=request.user, player_out=out_name, player_in=in_name)

        else:
            return Response({'detail': f'Unknown mode: {mode}'}, status=status.HTTP_400_BAD_REQUEST)

        team.players = players
        team.budget = current_budget
        team.save(update_fields=['players', 'budget'])
        print(f"[Transfer] Done. budget={current_budget} players={len(team.players)}")

        return Response({
            'message': 'Transfer completed successfully.',
            'budget': float(team.budget),
            'team': team.players,
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


class LeaderboardView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        try:
            teams = UserTeam.objects.all().order_by('-points')
            leaderboard = []
            for i, team in enumerate(teams):
                leaderboard.append({
                    'rank': i + 1,
                    'username': team.user.username,
                    'points': team.points,
                    'is_me': team.user == request.user
                })
            return Response(leaderboard)
        except Exception as e:
            import traceback
            print(f"ERROR in LeaderboardView: {e}")
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

        players = team.players or []
        for day in days_to_process:
            day_matches = matches_by_day[day]
            
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
                player_id = p.get('id')
                player_obj = Player.objects.filter(player_api_id=player_id).first()
                if player_obj and player_obj.team_api_id in results:
                    new_points += results[player_obj.team_api_id]
            
            processed.add(day)

        team.points += new_points
        team.processed_matchweeks = sorted(list(processed))
        team.last_synced_at = timezone.now()
        team.save()

        # Update ranks for all users
        all_teams = UserTeam.objects.all().order_by('-points')
        for i, t in enumerate(all_teams):
            t.rank = str(i + 1)
            t.save(update_fields=['rank'])
            
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
            'processed_matchweeks': team.processed_matchweeks
        })
