from django.db import models


class TimestampedModel(models.Model):
    """Abstract base — adds created_at / updated_at to concrete models."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
