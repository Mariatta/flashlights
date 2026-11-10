/* The countdown on the email code page. allauth sends one email per
 * address every ten seconds, so right after a code goes out the page shows
 * a line with data-new-code-wait="<seconds>" and a data-new-code-clock
 * span. This script counts the clock down and keeps "Send me a new code"
 * (the button for the form with id "resend") disabled until it reaches
 * zero, then hides the line and enables the button. Without the script the
 * button stays enabled, and an early click gets the 429 page. */
(function () {
    "use strict";
    var line = document.querySelector("[data-new-code-wait]");
    if (!line) return;
    var clock = line.querySelector("[data-new-code-clock]");
    var button = document.querySelector('button[form="resend"]');
    var end = Date.now() + Number(line.dataset.newCodeWait) * 1000;

    function tick() {
        var left = Math.max(0, Math.ceil((end - Date.now()) / 1000));
        clock.textContent = Math.floor(left / 60) + ":" + String(left % 60).padStart(2, "0");
        if (left > 0) {
            if (button) button.disabled = true;
            setTimeout(tick, 250);
            return;
        }
        line.hidden = true;
        if (button) button.disabled = false;
    }
    tick();
})();
