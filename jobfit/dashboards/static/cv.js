document.querySelectorAll('.seg-ctrl').forEach(function(ctrl){
  ctrl.querySelectorAll('.seg-btn').forEach(function(btn){
    btn.addEventListener('click',function(){
      ctrl.querySelectorAll('.seg-btn').forEach(function(b){b.classList.remove('active');});
      btn.classList.add('active');
      var mode=btn.dataset.mode;
      var section=ctrl.closest('[data-view]');
      section.querySelectorAll('.market-chart').forEach(function(el){
        el.style.display=mode==='market'?'':'none';
      });
      section.querySelectorAll('.top10-chart').forEach(function(el){
        el.style.display=mode==='top10'?'':'none';
      });
    });
  });
});
