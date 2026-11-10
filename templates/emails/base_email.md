{% load i18n %}{% autoescape off %}{% block content %}{% endblock content %}

---

**{{ brand.title }}** · [{{ current_site.domain }}](https://{{ current_site.domain }}){% if active_conference.website_url %} · {% blocktrans with name=brand.short_name %}{{ name }} website{% endblocktrans %}: <{{ active_conference.website_url }}>{% endif %}
{% endautoescape %}
