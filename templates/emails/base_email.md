{% load i18n %}{% autoescape off %}{% block content %}{% endblock content %}

---

**{{ brand.title }}** · [{{ current_site.domain }}](https://{{ current_site.domain }}){% if brand.website_url %} · {% blocktrans with name=brand.short_name %}{{ name }} website{% endblocktrans %}: <{{ brand.website_url }}>{% endif %}
{% endautoescape %}
