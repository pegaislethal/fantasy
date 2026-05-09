from django.db import models
from django.contrib.auth.models import AbstractUser
from decimal import Decimal


class User(AbstractUser):
    """Application users; documents are stored in the MongoDB `Users` collection."""
    two_factor_code = models.CharField(max_length=6, blank=True, null=True)
    two_factor_expiry = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'Users'


class AdminProfile(models.Model):
    """
    Admin records in the `Admin` collection. Create rows manually in MongoDB Compass
    or via Django admin; there is no signup API for this model.
    """

    email = models.EmailField(unique=True)
    name = models.CharField(max_length=150, blank=True)
    notes = models.TextField(blank=True)
    two_factor_code = models.CharField(max_length=6, blank=True, null=True)
    two_factor_expiry = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'Admin'

    def __str__(self):
        return self.email


class UserTeam(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='team')
    # Upgraded budget to max_digits 12 to support $100,000,000.00 exact amounts
    budget = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('100000000.00'))
    free_transfers = models.PositiveIntegerField(default=1)
    players = models.JSONField(default=list, blank=True) # { "squad": [{ "id": 1, "position": "GK", "is_bench": false }] }
    formation = models.CharField(max_length=20, default='4-4-2')
    points = models.PositiveIntegerField(default=0) # Total points accumulated
    processed_matchweeks = models.JSONField(default=list, blank=True) # [1, 2, 3, ...]
    rank = models.CharField(max_length=50, default='-')
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'UserTeams'


class TransferRecord(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transfer_records')
    player_out = models.CharField(max_length=120)
    player_in = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'TransferRecords'


class Player(models.Model):
    """
    Globally synchronized players from the football API.
    """
    player_api_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=150)
    position = models.CharField(max_length=50) # Goalkeeper, Defender, Midfielder, Offence
    date_of_birth = models.DateField(null=True, blank=True)
    nationality = models.CharField(max_length=100, blank=True)
    team_name = models.CharField(max_length=150, blank=True)
    team_api_id = models.IntegerField(null=True, blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('5000000.00'))

    class Meta:
        db_table = 'Players'

    def __str__(self):
        return f"{self.name} ({self.team_name})"
