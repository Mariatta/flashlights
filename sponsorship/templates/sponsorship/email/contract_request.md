Hello,

An approved sponsorship from **{{ profile.organization_name }}** for {{ profile.conference.name }} needs its contract and invoice. The details:

## Sponsorship

- **Company name:** {{ profile.organization_name }}
- **Company address:** {{ profile.organization_address }}
- **Tier:** {{ profile.sponsorship_tier.name }}
- **Amount:** ${{ profile.sponsorship_tier.amount }}{% if profile.sponsorship_override_amount %} (agreed amount: ${{ profile.sponsorship_override_amount }}){% endif %}
- **Contact name:** {{ profile.sponsor_contact_name }}
- **Contact email:** {{ profile.sponsors_contact_email }}

Reply to this email if anything is missing.

The {{ profile.conference.name }} team
