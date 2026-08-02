(() => {
  const BACK_JUMP_URL = "hijacked.html";
  const urlNow = document.getElementById("url-now");
  const hijackState = document.getElementById("hijack-state");
  const fakeBackBtn = document.getElementById("fake-back");
  const disarmBtn = document.getElementById("disarm");
  const hint = document.getElementById("hint");

  let armed = true;
  let onPopState = null;

  function refreshUrl() {
    urlNow.textContent = location.href;
  }

  function arm() {
    armed = true;
    hijackState.textContent = "已武装";
    hijackState.className = "armed";
    fakeBackBtn.disabled = false;
    hint.textContent = "也可以直接点浏览器左上角的 ← 后退按钮试一次。";

    try {
      // 与真实落地页同构：塞一条带 # 的假历史
      history.pushState("forward", null, "#");
      refreshUrl();

      onPopState = function () {
        if (!armed) return;
        location.href = BACK_JUMP_URL;
      };
      window.addEventListener("popstate", onPopState, false);
    } catch (err) {
      hijackState.textContent = "武装失败";
      console.error(err);
    }
  }

  function disarm() {
    armed = false;
    if (onPopState) {
      window.removeEventListener("popstate", onPopState, false);
      onPopState = null;
    }
    hijackState.textContent = "已解除";
    hijackState.className = "disarmed";
    fakeBackBtn.disabled = true;
    hint.textContent = "劫持已关闭。现在点后退会按正常历史返回（可能回到入口页）。";
  }

  // 模拟后退：history.back() 会触发 popstate
  fakeBackBtn.addEventListener("click", () => {
    if (!armed) return;
    history.back();
  });

  disarmBtn.addEventListener("click", disarm);

  refreshUrl();
  arm();
})();
