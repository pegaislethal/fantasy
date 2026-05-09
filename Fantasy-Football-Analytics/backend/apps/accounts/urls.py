from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    AdminStatsView,
    AdminUserDetailView,
    AdminUsersView,
    DirectLoginView,
    EmailTokenObtainPairView,
    GoogleLoginView,
    RegisterView,
    Request2FAView,
    RequestSignupCodeView,
    UserDashboardView,
    UserMatchesView,
    UserTeamView,
    UserTransferMarketView,
    UserTransferSubmitView,
    Verify2FAView,
    ProfileUpdateView,
    ChangePasswordView,
    LeaderboardView,
    SyncPointsView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('register/code/', RequestSignupCodeView.as_view(), name='register_code'),
    path('auth/login/', DirectLoginView.as_view(), name='direct_login'),
    path('auth/google/', GoogleLoginView.as_view(), name='google_login'),
    path('token/', EmailTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/2fa/request/', Request2FAView.as_view(), name='2fa_request'),
    path('auth/2fa/verify/', Verify2FAView.as_view(), name='2fa_verify'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('admin/stats/', AdminStatsView.as_view(), name='admin_stats'),
    path('admin/users/', AdminUsersView.as_view(), name='admin_users'),
    path('admin/users/<str:user_id>/', AdminUserDetailView.as_view(), name='admin_user_detail'),
    path('user/dashboard/', UserDashboardView.as_view(), name='user_dashboard'),
    path('user/team/', UserTeamView.as_view(), name='user_team'),
    path('user/matches/', UserMatchesView.as_view(), name='user_matches'),
    path('user/transfers/market/', UserTransferMarketView.as_view(), name='user_transfer_market'),
    path('players/', UserTransferMarketView.as_view(), name='players'),
    path('user/transfers/submit/', UserTransferSubmitView.as_view(), name='user_transfer_submit'),
    path('user/profile/update/', ProfileUpdateView.as_view(), name='profile_update'),
    path('user/password/change/', ChangePasswordView.as_view(), name='password_change'),
    path('user/leaderboard/', LeaderboardView.as_view(), name='user_leaderboard'),
    path('user/sync-points/', SyncPointsView.as_view(), name='user-sync-points'),
]

