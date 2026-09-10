(function () {
  var btn = document.querySelector("[data-nav-toggle]");
  var links = document.querySelector("[data-nav-links]");
  if (!btn || !links) return;
  btn.addEventListener("click", function () {
    var open = links.classList.toggle("open");
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  });
})();
