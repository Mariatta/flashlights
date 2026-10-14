/* Show a block only while a select holds a given value:
 * data-show-when="<select id>=<value>". Without JavaScript every block
 * stays visible, so the form still works. */
(function () {
    "use strict";
    var blocks = document.querySelectorAll("[data-show-when]");
    var update = function () {
        blocks.forEach(function (block) {
            var rule = block.dataset.showWhen.split("=");
            var field = document.getElementById(rule[0]);
            if (field) block.hidden = field.value !== rule[1];
        });
    };
    document.addEventListener("change", function (event) {
        if (event.target.matches("select")) update();
    });
    update();
})();
