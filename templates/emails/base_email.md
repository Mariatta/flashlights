{% load i18n %}{% autoescape off %}{% blocktrans with site_name=brand.title %}Hello from {{ site_name }}.{% endblocktrans %}

{% block content %}{% endblock content %}

---

{% blocktrans with site_name=brand.title site_domain=current_site.domain %}Thank you for using **{{ site_name }}**.

[{{ site_domain }}](https://{{ site_domain }}){% endblocktrans %}
{% endautoescape %}