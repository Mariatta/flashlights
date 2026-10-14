/* "Add another" row on a formset: clones the empty-form template with the
 * next index and bumps the management form's TOTAL_FORMS. Markup:
 * [data-formset] holding [data-formset-rows], a <template
 * data-formset-empty> and a [data-formset-add] button. */
(function () {
    "use strict";
    document.querySelectorAll("[data-formset]").forEach(function (block) {
        var rows = block.querySelector("[data-formset-rows]");
        var template = block.querySelector("[data-formset-empty]");
        var total = block.querySelector('input[name$="-TOTAL_FORMS"]');
        block.querySelector("[data-formset-add]").addEventListener("click", function () {
            var index = parseInt(total.value, 10);
            var html = template.innerHTML.replace(/__prefix__/g, String(index));
            rows.insertAdjacentHTML("beforeend", html);
            total.value = String(index + 1);
            var added = rows.lastElementChild.querySelector("input, select");
            if (added) {
                added.focus();
            }
        });
    });
})();
