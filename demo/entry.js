(() => {
  const DELAY_MS = 800;
  const countdownEl = document.getElementById("countdown");
  const startBtn = document.getElementById("start");
  const steps = [...document.querySelectorAll(".steps li")];

  let timer = null;
  let ticking = null;
  let running = false;

  function setActive(n) {
    steps.forEach((li) => {
      const step = Number(li.dataset.step);
      li.classList.toggle("active", step === n);
      li.classList.toggle("done", step < n);
    });
  }

  function start() {
    if (running) return;
    running = true;
    startBtn.disabled = true;
    startBtn.textContent = "跳转中…";

    setActive(2);

    window.setTimeout(() => {
      setActive(3);
      const started = Date.now();

      ticking = window.setInterval(() => {
        const left = Math.max(0, DELAY_MS - (Date.now() - started));
        countdownEl.textContent = String(left);
      }, 30);

      timer = window.setTimeout(() => {
        window.clearInterval(ticking);
        countdownEl.textContent = "0";
        setActive(4);
        window.location.href = "landing.html";
      }, DELAY_MS);
    }, 350);
  }

  startBtn.addEventListener("click", start);

  // 带 ?auto=1 时自动开始，方便连跑全流程
  if (new URLSearchParams(location.search).has("auto")) {
    start();
  }
})();
