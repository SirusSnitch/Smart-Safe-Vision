from django.contrib.auth.tokens import PasswordResetTokenGenerator

class TokenGeneratorPassword(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return (
            str(user.pk) + user.email + str(timestamp) +
            str(user.is_verified)
        )

password_reset_token = TokenGeneratorPassword()
