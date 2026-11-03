// Visualize Playwright's automated pointer in headed browser windows and recordings.
// Loaded by Playwright MCP only when INSIGHT_SHOW_BROWSER_CURSOR=1.
(() => {
  const hostId = "__insight_ai_cursor_overlay__";
  if (document.getElementById(hostId)) return;

  const host = document.createElement("div");
  host.id = hostId;
  host.setAttribute("aria-hidden", "true");
  host.style.cssText =
    "all:initial!important;display:block!important;position:fixed!important;inset:0!important;width:100vw!important;height:100vh!important;z-index:2147483647!important;pointer-events:none!important;overflow:hidden!important;";

  const shadow = host.attachShadow({ mode: "closed" });
  shadow.innerHTML = `
    <style>
      :host { all: initial; }
      .pointer {
        position: fixed;
        left: 0;
        top: 0;
        width: 28px;
        height: 36px;
        opacity: 0;
        transform: translate3d(-100px, -100px, 0);
        transition: transform 65ms ease-out, opacity 90ms ease;
        will-change: transform;
      }
      .pointer.visible { opacity: 1; }
      .pointer svg { display: block; width: 100%; height: 100%; overflow: visible; }
      .click-ring {
        position: fixed;
        width: 24px;
        height: 24px;
        margin: -12px 0 0 -12px;
        border: 2px solid #ff4d6d;
        border-radius: 50%;
        opacity: 0;
        transform: scale(.35);
      }
      .click-ring.pulse { animation: insight-click 420ms ease-out; }
      @keyframes insight-click {
        0% { opacity: .95; transform: scale(.35); }
        100% { opacity: 0; transform: scale(1.7); }
      }
      @media (prefers-reduced-motion: reduce) {
        .pointer { transition: opacity 90ms ease; }
      }
    </style>
    <div class="pointer">
      <svg viewBox="0 0 28 36" aria-hidden="true">
        <path d="M3 2v25l6.8-6.6 5 11 4.5-2.1-5.3-10.8 9.6-.3L3 2z"
          fill="#fff" stroke="#172033" stroke-width="3" stroke-linejoin="round"/>
        <path d="M4.5 5.5v17.9l5.1-4.9 5.1 10.8 2.2-1-5.2-10.8 7.8-.2L4.5 5.5z"
          fill="#36a3ff"/>
      </svg>
    </div>
    <div class="click-ring"></div>
  `;

  const pointer = shadow.querySelector(".pointer");
  const ring = shadow.querySelector(".click-ring");
  let ringTimer;

  const install = () => {
    if (!document.documentElement || host.isConnected) return;
    document.documentElement.appendChild(host);
  };

  install();
  document.addEventListener("DOMContentLoaded", install, { once: true });

  const move = (event) => {
    install();
    pointer.style.transform = `translate3d(${event.clientX - 3}px, ${event.clientY - 2}px, 0)`;
    pointer.classList.add("visible");
  };

  document.addEventListener("pointermove", move, true);
  document.addEventListener("mousemove", move, true);
  document.addEventListener("click", (event) => {
    install();
    ring.style.left = `${event.clientX}px`;
    ring.style.top = `${event.clientY}px`;
    ring.classList.remove("pulse");
    // Restart the animation even when clicks happen in quick succession.
    void ring.offsetWidth;
    ring.classList.add("pulse");
    clearTimeout(ringTimer);
    ringTimer = setTimeout(() => ring.classList.remove("pulse"), 450);
  }, true);
})();
