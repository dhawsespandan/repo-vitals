"""factory_boy factories. Grows with the schema each phase."""

from __future__ import annotations

import factory

from apps.accounts.crypto import encrypt_token
from apps.accounts.models import User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("github_user_id",)

    github_user_id = factory.Sequence(lambda n: 1000 + n)
    github_username = factory.Sequence(lambda n: f"dev-user-{n}")
    display_name = factory.LazyAttribute(
        lambda o: o.github_username.replace("-", " ").title()
    )
    email = factory.LazyAttribute(lambda o: f"{o.github_username}@example.com")
    avatar_url = factory.LazyAttribute(
        lambda o: f"https://avatars.githubusercontent.com/u/{o.github_user_id}"
    )
    encrypted_github_token = factory.LazyFunction(
        lambda: encrypt_token("gho_testtokentesttokentesttoken00000000")
    )
    token_scopes = "repo,read:user,user:email"
