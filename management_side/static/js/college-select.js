(function () {
    // Remember the college this browser used last, so people only pick it once.
    var KEY = "smc-college";
    document.querySelectorAll("select.college-select").forEach(function (select) {
        try {
            var saved = localStorage.getItem(KEY);
            if (!select.value && saved && select.querySelector('option[value="' + saved + '"]')) {
                select.value = saved;
            }
            select.addEventListener("change", function () {
                if (select.value) { localStorage.setItem(KEY, select.value); }
            });
        } catch (e) { /* storage unavailable: nothing to remember */ }
    });
})();
