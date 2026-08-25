from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Accounts"

    def ready(self) -> None:
        # Registers the login receiver that captures and encrypts the GitHub
        # access token. Import for side effects only.
        from . import signals  # noqa: F401
