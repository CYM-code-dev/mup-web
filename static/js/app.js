// 引导: 模式 (single/multi) 切换 + Tab 切换 + init。
const modeInit = sessionStorage.getItem("mode") || "single";
document.querySelectorAll('input[name="mode"]').forEach(r => { if (r.value === modeInit) r.checked = true; });
document.querySelectorAll('input[name="mode"]').forEach(r => {
  r.addEventListener("change", () => { sessionStorage.setItem("mode", r.value); location.hash = ""; location.reload(); });
});

document.getElementById("tabs").addEventListener("click", e => {
  if (e.target.tagName !== "BUTTON") return;
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("active", b === e.target));
  document.querySelectorAll("main .tab").forEach(s => { s.hidden = s.id !== e.target.dataset.tab; });
});

// 侧栏显隐 (持久化到 sessionStorage)
const sbBtn = document.getElementById("btn-sidebar");
if (sessionStorage.getItem("sidebar") === "0") document.body.classList.add("sidebar-collapsed");
sbBtn.addEventListener("click", () => {
  const collapsed = document.body.classList.toggle("sidebar-collapsed");
  sessionStorage.setItem("sidebar", collapsed ? "0" : "1");
});

(async () => {
  const mod = modeInit === "multi" ? await import('./multi.js') : await import('./single.js');
  await mod.init();
})();
