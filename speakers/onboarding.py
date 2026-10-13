"""Where a presenter finishes their account.

The portal-wide agreement gate (``portal_account.agreements``) asks each
resolver named in ``settings.ONBOARDING_URL_RESOLVERS`` where to send a user
who has not agreed yet. A presenter who is on the program gets the speaker
welcome page, which collects the agreements along with a username and an
optional password; everyone else, including someone waiting on an answer to
a proposal, gets the plain agreements page.
"""

from django.urls import reverse

from .editions import speaker_edition


def welcome_url_for(user):
    """The speaker welcome page when ``user`` is on the program of the active
    edition or a newer one they were invited to, else None. Someone whose
    proposal nobody has answered gets the plain agreements page, and the
    speaker welcome when their session is approved (``speaker_edition``
    applies the same rule as the speaker pages' gate)."""
    if speaker_edition(user) is None:
        return None
    return reverse("speakers:my_welcome")
