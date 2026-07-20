
var _activeFilters={seniority:new Set(),stage:new Set(),mode:new Set()};
function applyFilters(){
    var any=Object.keys(_activeFilters).some(function(k){return _activeFilters[k].size>0;});
    document.getElementById('flt-clear').style.display=any?'':'none';
    document.querySelectorAll('tbody tr').forEach(function(row){
        if(!any){row.style.display='';return;}
        var show=true;
        for(var k in _activeFilters){
            if(_activeFilters[k].size===0)continue;
            var v=(row.dataset[k]||'').toLowerCase();
            if(!_activeFilters[k].has(v)){show=false;break;}
        }
        row.style.display=show?'':'none';
    });
}
function toggleFilter(key,val,btn){
    if(_activeFilters[key].has(val)){_activeFilters[key].delete(val);btn.classList.remove('active');}
    else{_activeFilters[key].add(val);btn.classList.add('active');}
    applyFilters();
}
function clearFilters(){
    for(var k in _activeFilters)_activeFilters[k].clear();
    document.querySelectorAll('.flt-pill').forEach(function(b){b.classList.remove('active');});
    applyFilters();
}
function syncStarredCount(){
    fetch('/api/starred-status?role={{ role_slug }}')
        .then(function(r){return r.ok?r.json():{starred:[]};} )
        .then(function(data){
            var count=data.starred.length;
            var n=document.querySelector('.tab-n[data-tier="starred"]');
            var k=document.querySelector('.kpi[data-tier="starred"] .kpi-n');
            if(n)n.textContent=count;
            if(k)k.textContent=count;
        }).catch(function(){});
}
setView('starred');
function sortTierTable(id, col, isNum) {
    var tbl = document.getElementById(id);
    if (!tbl) return;
    var tbody = tbl.querySelector('tbody');
    var rows = Array.from(tbody.querySelectorAll('tr'));
    var ths = tbl.querySelectorAll('th');
    var th = ths[col];
    var asc = th.dataset.dir !== 'asc';
    ths.forEach(function(h) { h.dataset.dir = ''; h.classList.remove('sort-asc','sort-desc'); });
    th.dataset.dir = asc ? 'asc' : 'desc';
    th.classList.add(asc ? 'sort-asc' : 'sort-desc');
    rows.sort(function(a, b) {
        var av = a.cells[col].dataset.val || '';
        var bv = b.cells[col].dataset.val || '';
        if (isNum) { av = parseFloat(av) || 0; bv = parseFloat(bv) || 0; }
        if (av < bv) return asc ? -1 : 1;
        if (av > bv) return asc ? 1 : -1;
        return 0;
    });
    rows.forEach(function(r) { tbody.appendChild(r); });
}
fetch('/api/read-status?role={{ role_slug }}')
    .then(function(r){return r.ok?r.json():{read:[]};} )
    .then(function(data){
        var s=new Set(data.read);
        document.querySelectorAll('.read-cb').forEach(function(cb){
            if(!s.has(cb.dataset.refnr))return;
            var row=cb.closest('tr'),tbody=row.closest('tbody');
            cb.checked=true;
            row.style.opacity='0.4';
            tbody.appendChild(row);
        });
    }).catch(function(){});
document.querySelectorAll('.read-cb').forEach(function(cb){
    cb.addEventListener('change',function(){
        var refnr=this.dataset.refnr;
        var row=this.closest('tr'),tbody=row.closest('tbody');
        var method=this.checked?'POST':'DELETE';
        fetch('/api/read/'+encodeURIComponent(refnr),{method:method})
            .then(function(r){
                if(!r.ok)return;
                if(method==='POST'){row.style.opacity='0.4';tbody.appendChild(row);}
                else{row.style.opacity='';tbody.insertBefore(row,tbody.firstChild);}
            });
    });
});
fetch('/api/starred-status?role={{ role_slug }}')
    .then(function(r){return r.ok?r.json():{starred:[]};} )
    .then(function(data){
        var s=new Set(data.starred);
        document.querySelectorAll('.star-btn').forEach(function(btn){
            if(!s.has(btn.dataset.refnr))return;
            btn.textContent='★';btn.style.color='#f59e0b';
            btn.closest('tr').style.background='#fffbeb';
        });
    }).catch(function(){});
var _TIER_BADGES={
    dreamjob: {l:'Dreamjob',  s:'background:#e4f5ed;color:#1a7a4e',v:0},
    cvbuilder:{l:'CV Builder',s:'background:#ebf2ff;color:#1e56b0',v:1},
    easywin:  {l:'Easy Win',  s:'background:#fff4e6;color:#b45309',v:2},
    skip:     {l:'Skip',      s:'background:#f4f6fa;color:#6b7a95',v:3}
};
document.addEventListener('click',function(e){
    var cvBtn=e.target.closest('.cv-btn');
    if(cvBtn&&!e.target.closest('a')){
        var refnr=cvBtn.dataset.refnr;
        var role='{{ role_slug }}';
        var orig=cvBtn.textContent;
        cvBtn.textContent='…';
        cvBtn.style.pointerEvents='none';
        cvBtn.style.color='#9ca3af';
        fetch('/api/cv/'+encodeURIComponent(refnr)+'/generate?role='+encodeURIComponent(role),{method:'POST'})
            .then(function(r){
                if(!r.ok)return r.text().then(function(t){throw new Error(t);});
                return r.json();
            })
            .then(function(data){
                if(data.status==='ready'){
                    cvBtn.innerHTML='<a href="'+data.url+'" style="color:#27a269;text-decoration:none;font-weight:600" title="Download CV PDF">DL</a>';
                    cvBtn.style.pointerEvents='';cvBtn.style.color='';
                    return;
                }
                var attempts=0,maxAttempts=40;
                var pollId=setInterval(function(){
                    attempts++;
                    if(attempts>maxAttempts){
                        clearInterval(pollId);
                        cvBtn.textContent='!';cvBtn.style.color='#e05252';
                        cvBtn.title='Generation timed out';
                        setTimeout(function(){cvBtn.textContent=orig;cvBtn.style.color='#9ca3af';cvBtn.style.pointerEvents='';cvBtn.title='Generate tailored CV (PDF)';},5000);
                        return;
                    }
                    fetch('/api/cv/'+encodeURIComponent(refnr)+'/status?role='+encodeURIComponent(role))
                        .then(function(r){return r.ok?r.json():{status:'generating'};})
                        .then(function(data){
                            if(data.status==='ready'){
                                clearInterval(pollId);
                                cvBtn.innerHTML='<a href="'+data.url+'" style="color:#27a269;text-decoration:none;font-weight:600" title="Download CV PDF">DL</a>';
                                cvBtn.style.pointerEvents='';cvBtn.style.color='';
                            } else if(data.status==='failed'){
                                clearInterval(pollId);
                                cvBtn.textContent='!';cvBtn.style.color='#e05252';
                                cvBtn.title='Generation failed (check logs)';
                                setTimeout(function(){cvBtn.textContent=orig;cvBtn.style.color='#9ca3af';cvBtn.style.pointerEvents='';cvBtn.title='Generate tailored CV (PDF)';},5000);
                            }
                        }).catch(function(){});
                },3000);
            })
            .catch(function(err){
                console.error('CV generation failed:',err);
                cvBtn.textContent='!';
                cvBtn.style.color='#e05252';
                cvBtn.title='Error: '+err.message;
                setTimeout(function(){cvBtn.textContent=orig;cvBtn.style.color='#9ca3af';cvBtn.style.pointerEvents='';cvBtn.title='Generate tailored CV (PDF)';},5000);
            });
        return;
    }
    var asBtn=e.target.closest('.anschreiben-btn');
    if(asBtn&&!e.target.closest('a')){
        var refnr=asBtn.dataset.refnr;
        var role='{{ role_slug }}';
        var orig=asBtn.textContent;
        asBtn.textContent='…';
        asBtn.style.pointerEvents='none';
        asBtn.style.color='#9ca3af';
        fetch('/api/anschreiben/'+encodeURIComponent(refnr)+'/generate?role='+encodeURIComponent(role),{method:'POST'})
            .then(function(r){
                if(!r.ok)return r.text().then(function(t){throw new Error(t);});
                return r.json();
            })
            .then(function(data){
                if(data.status==='ready'){
                    asBtn.innerHTML='<a href="'+data.url+'" style="color:#27a269;text-decoration:none;font-weight:600" title="Download Anschreiben PDF">DL</a>';
                    asBtn.style.pointerEvents='';asBtn.style.color='';
                    return;
                }
                var attempts=0,maxAttempts=40;
                var pollId=setInterval(function(){
                    attempts++;
                    if(attempts>maxAttempts){
                        clearInterval(pollId);
                        asBtn.textContent='!';asBtn.style.color='#e05252';
                        asBtn.title='Generation timed out';
                        setTimeout(function(){asBtn.textContent=orig;asBtn.style.color='#9ca3af';asBtn.style.pointerEvents='';asBtn.title='Generate Anschreiben (PDF)';},5000);
                        return;
                    }
                    fetch('/api/anschreiben/'+encodeURIComponent(refnr)+'/status?role='+encodeURIComponent(role))
                        .then(function(r){return r.ok?r.json():{status:'generating'};})
                        .then(function(data){
                            if(data.status==='ready'){
                                clearInterval(pollId);
                                asBtn.innerHTML='<a href="'+data.url+'" style="color:#27a269;text-decoration:none;font-weight:600" title="Download Anschreiben PDF">DL</a>';
                                asBtn.style.pointerEvents='';asBtn.style.color='';
                            } else if(data.status==='failed'){
                                clearInterval(pollId);
                                asBtn.textContent='!';asBtn.style.color='#e05252';
                                asBtn.title='Generation failed (check logs)';
                                setTimeout(function(){asBtn.textContent=orig;asBtn.style.color='#9ca3af';asBtn.style.pointerEvents='';asBtn.title='Generate Anschreiben (PDF)';},5000);
                            }
                        }).catch(function(){});
                },3000);
            })
            .catch(function(err){
                console.error('Anschreiben generation failed:',err);
                asBtn.textContent='!';
                asBtn.style.color='#e05252';
                asBtn.title='Error: '+err.message;
                setTimeout(function(){asBtn.textContent=orig;asBtn.style.color='#9ca3af';asBtn.style.pointerEvents='';asBtn.title='Generate Anschreiben (PDF)';},5000);
            });
        return;
    }
    var btn=e.target.closest('.star-btn');
    if(!btn)return;
    var refnr=btn.dataset.refnr;
    var row=btn.closest('tr');
    var starred=btn.textContent==='★';
    var method=starred?'DELETE':'POST';
    fetch('/api/starred/'+encodeURIComponent(refnr),{method:method})
        .then(function(r){
            if(!r.ok)return;
            if(method==='POST'){
                btn.textContent='★';btn.style.color='#f59e0b';
                row.style.background='#fffbeb';
                var tierView=row.closest('[data-view]');
                var tierKey=tierView?tierView.dataset.view:'';
                var st=document.getElementById('tbl-starred');
                if(st&&tierKey&&tierKey!=='starred'){
                    var tb=_TIER_BADGES[tierKey]||{l:tierKey,s:'background:#f4f6fa;color:#6b7a95',v:9};
                    var clone=row.cloneNode(true);
                    var td=document.createElement('td');
                    td.dataset.val=tb.v;
                    td.innerHTML='<span style="'+tb.s+';border-radius:4px;padding:1px 7px;font-size:11px;font-weight:500;white-space:nowrap">'+tb.l+'</span>';
                    clone.insertBefore(td,clone.cells[1]);
                    var cb=clone.querySelector('.star-btn');
                    if(cb){cb.textContent='★';cb.style.color='#f59e0b';}
                    clone.style.background='#fffbeb';
                    st.querySelector('tbody').insertBefore(clone,st.querySelector('tbody').firstChild);
                }
                syncStarredCount();
            }else{
                document.querySelectorAll('.star-btn[data-refnr="'+refnr+'"]').forEach(function(b){
                    b.textContent='☆';b.style.color='#d1d5db';
                    b.closest('tr').style.background='';
                });
                var st2=document.getElementById('tbl-starred');
                if(st2)st2.querySelectorAll('.star-btn[data-refnr="'+refnr+'"]').forEach(function(b){b.closest('tr').remove();});
                syncStarredCount();
            }
        });
});
