/* "Add another" affiliation row: clones the empty-form template with the
   next index and bumps the management form's TOTAL_FORMS. */
(function () {
    var card = document.querySelector("[data-affiliations]");
    if (!card) {
        return;
    }
    var rows = card.querySelector("[data-affiliation-rows]");
    var template = card.querySelector("[data-affiliation-empty]");
    var total = card.querySelector('input[name$="-TOTAL_FORMS"]');
    card.querySelector("[data-affiliation-add]").addEventListener("click", function () {
        var index = parseInt(total.value, 10);
        var html = template.innerHTML.replace(/__prefix__/g, String(index));
        rows.insertAdjacentHTML("beforeend", html);
        total.value = String(index + 1);
        var added = rows.lastElementChild.querySelector("input, select");
        if (added) {
            added.focus();
        }
    });
})();
