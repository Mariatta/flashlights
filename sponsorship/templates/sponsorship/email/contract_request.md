Hello,

An approved sponsorship from **{{ profile.organization_name }}** for {{ profile.conference.name }} needs its contract and invoice. The details:

## Sponsorship

- **Company name:** {{ profile.organization_name }}{% if profile.organization_address %}
- **Company address:** {{ profile.organization_address }}{% endif %}{% if profile.sponsorship_tier %}
- **Tier:** {{ profile.sponsorship_tier.name }}
- **Amount:** ${{ profile.sponsorship_tier.amount }}{% if profile.sponsorship_override_amount %} (agreed amount: ${{ profile.sponsorship_override_amount }}){% endif %}{% endif %}{% if profile.sponsor_contact_name %}
- **Contact name:** {{ profile.sponsor_contact_name }}{% endif %}{% if profile.sponsors_contact_email %}
- **Contact email:** {{ profile.sponsors_contact_email }}{% endif %}

Reply to this email if anything is missing.

The {{ profile.conference.name }} team
