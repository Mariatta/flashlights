Hello,

The sponsorship from **{{ profile.organization_name }}** for {{ profile.conference.name }} is approved.
{% if profile.sponsorship_tier or profile.sponsor_contact_name or profile.sponsors_contact_email %}
{% if profile.sponsorship_tier %}- **Tier:** {{ profile.sponsorship_tier.name }}
- **Amount:** ${{ profile.sponsorship_tier.amount }}{% if profile.sponsorship_override_amount %} (agreed amount: ${{ profile.sponsorship_override_amount }}){% endif %}
{% endif %}{% if profile.sponsor_contact_name %}- **Contact name:** {{ profile.sponsor_contact_name }}
{% endif %}{% if profile.sponsors_contact_email %}- **Contact email:** {{ profile.sponsors_contact_email }}
{% endif %}{% endif %}
The next step is the contract: request it from the sponsor's page in the portal.

The {{ profile.conference.name }} team
