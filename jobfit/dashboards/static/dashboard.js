// ── Loading indicator on sidebar navigation ───────────────────────────────────
document.querySelectorAll('.nav-item').forEach(function(a) {
  a.addEventListener('click', function() {
    if (!this.classList.contains('active')) {
      document.documentElement.classList.add('nav-loading');
    }
  });
});

// ── setView (data-view tabs) ──────────────────────────────────────────────────
function setView(v){
  document.querySelectorAll('[data-view]').forEach(function(el){
    if(el.tagName==='BUTTON'){
      el.classList.toggle('active',el.dataset.view===v);
    } else {
      el.style.display=el.dataset.view===v?'':'none';
    }
  });
}

// ── Drawer system ─────────────────────────────────────────────────────────────
var _currentDrawer=null;
function openDrawer(id){
  if(_currentDrawer)document.getElementById(_currentDrawer).classList.remove('open');
  _currentDrawer=id;
  document.getElementById(id).classList.add('open');
  document.getElementById('_overlay').classList.add('open');
  document.body.style.overflow='hidden';
}
function closeDrawer(){
  if(_currentDrawer)document.getElementById(_currentDrawer).classList.remove('open');
  document.getElementById('_overlay').classList.remove('open');
  document.body.style.overflow='';
  _currentDrawer=null;
}
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeDrawer();});

// ── Generic tab groups (.tabs, .plat-tabs) ────────────────────────────────────
document.querySelectorAll('.tabs,.plat-tabs').forEach(function(grp){
  grp.querySelectorAll('.tab').forEach(function(tab){
    tab.addEventListener('click',function(){
      grp.querySelectorAll('.tab').forEach(function(t){t.classList.remove('active');});
      tab.classList.add('active');
    });
  });
});
