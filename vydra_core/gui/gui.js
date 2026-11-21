(()=>{
const $=id=>document.getElementById(id);
let desktopRuns=null;
let config=null,runs=[],activeId=null,browseTarget=null,parentPath=null,logShown=false,polling=false,submitting=false;
try{document.documentElement.dataset.theme=localStorage.getItem('vydra-gui-theme')||'dark'}catch{}
function theme(){ $('theme').textContent=document.documentElement.dataset.theme==='dark'?'Switch to light':'Switch to dark' }
theme();$('theme').onclick=()=>{document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark';try{localStorage.setItem('vydra-gui-theme',document.documentElement.dataset.theme)}catch{}theme()};
async function api(path,body){const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Vydra-Token':config.token},body:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw new Error(data.error||'Request failed');return data}
function inputMode(){const folder=$('mode').value==='folder';$('source-label').textContent=folder?'Input folder':'Input FASTA file';$('input-hint').textContent=folder?'FASTA files are discovered recursively. Original file names and folders are retained.':'Select a protein FASTA file. Original IDs and headers are retained.'}
$('mode').onchange=inputMode;
const active=r=>['starting','running','cancelling'].includes(r.status);
function showReport(run){window.location.assign('/reports/'+encodeURIComponent(run.id)+'/')}
function selectRun(id){activeId=id;logShown=false;$('execution-log').hidden=true;render()}
function render(){
 const busy=runs.some(active);$('start').disabled=!config||(!desktopRuns&&busy)||submitting;
 if(desktopRuns)$('start').textContent=busy||runs.some(r=>r.status==='queued')?'Add to queue':'Start task';
 const run=runs.find(r=>r.id===activeId)||runs.find(active)||runs[0];if(run)activeId=run.id;
 if(desktopRuns)desktopRuns.render(runs);
 else {
 $('recent').replaceChildren();if(!runs.length){const p=document.createElement('p');p.className='muted';p.textContent='No runs yet.';$('recent').append(p)}
 runs.forEach(r=>{const button=document.createElement('button');button.type='button';const title=document.createElement('span');title.className='recent-title';const date=document.createElement('span');date.textContent=new Date(r.created_at).toLocaleString('en');const status=document.createElement('span');status.textContent=r.status[0].toUpperCase()+r.status.slice(1);title.append(date,status);const path=document.createElement('small');path.textContent=r.input;button.append(title,path);button.title=['complete','completed'].includes(r.status)&&r.report_path?'Open inference results':'Inspect run status';button.onclick=()=>{if(['complete','completed'].includes(r.status)&&r.report_path){window.location.assign('/reports/'+encodeURIComponent(r.id)+'/');return}activeId=r.id;logShown=false;$('show-log').textContent='View execution log';$('execution-log').hidden=true;render();$('status-section').scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'})};$('recent').append(button)});
 }
 if(!run)return;
 if(desktopRuns)desktopRuns.showDetails(run);
 $('status-badge').textContent=run.status[0].toUpperCase()+run.status.slice(1);$('status-text').textContent=run.stage;
 $('resume').hidden=!['cancelled','failed','interrupted'].includes(run.status)||(desktopRuns&&!run.started_timestamp);$('resume').disabled=(!desktopRuns&&busy)||submitting;
 const storage=run.storage_estimate; $('storage-estimate').textContent=storage?`Disk space: ${storage.sequences.toLocaleString('en')} proteins · embedding checkpoint ${(storage.checkpoint_bytes/1024**3).toFixed(2)} GiB · estimated total ${(storage.estimated_total_bytes/1024**3).toFixed(2)} GiB (model downloads excluded)`:'';
 $('cancel').hidden=!active(run)&&run.status!=='queued';$('cancel').disabled=run.status==='cancelling';$('show-log').disabled=!!desktopRuns&&!run.started_timestamp;
 $('run-error').textContent=run.error||'';$('saved-output').textContent='Results folder: '+run.output;
 $('processed').textContent=Number.isInteger(run.processed)?`Processed proteins: ${run.processed.toLocaleString('en')} / ${run.total?.toLocaleString('en')||'—'} · remaining: ${Math.max(0,(run.total||0)-run.processed).toLocaleString('en')}`:run.total?`Input proteins: ${run.total.toLocaleString('en')}`:'';
 const embedding=run.stage==='Generating embeddings', hasChunks=Number.isInteger(run.chunks_total);
 $('chunks').textContent=hasChunks?`Embedding chunks: ${(run.chunks_done||0).toLocaleString('en')} / ${run.chunks_total.toLocaleString('en')} · remaining: ${Math.max(0,run.chunks_total-(run.chunks_done||0)).toLocaleString('en')}`:'';
 const now=Date.now()/1000, age=run.last_progress_at?Math.max(0,Math.floor(now-run.last_progress_at)):null;
 $('checkpoint-status').textContent=run.checkpoint_saved_at?`Last confirmed checkpoint: ${new Date(run.checkpoint_saved_at*1000).toLocaleString('en')} · saved after each completed chunk batch / classified protein`:'No inference checkpoint confirmed yet.';
 $('activity-status').textContent=active(run)&&['Generating embeddings','Classifying proteins'].includes(run.stage)&&age!==null?`${run.batch_size_active?`Computing batch of ${run.batch_size_active} chunks. `:''}${age}s since last confirmed progress.${age>=300?' No work completed for at least 5 minutes. Review the execution log; the model may be slow or stalled. Resume reuses saved work.':''}`:'';
 const elapsed=active(run)?Math.max(0,now-run.started_timestamp):run.elapsed_seconds||0;
 $('elapsed').textContent='Elapsed: '+Math.floor(elapsed/60)+'m '+Math.floor(elapsed%60)+'s';
 $('progress').hidden=!(['Classifying proteins','Generating embeddings'].includes(run.stage)&&run.total>0);if(!$('progress').hidden){$('progress').max=embedding&&hasChunks?run.chunks_total:run.total;$('progress').value=embedding&&hasChunks?(run.chunks_done||0):(run.processed||0)}
}
async function poll(){if(polling)return;polling=true;try{runs=await api('/api/runs');if(desktopRuns)$('desktop-connection-error').textContent='';render();if(logShown&&activeId){const data=await api('/api/log/'+activeId);$('execution-log').textContent=data.log||'No log output yet.'}}catch(e){if(desktopRuns)$('desktop-connection-error').textContent='Connection to Vydra lost. '+e.message;else $('form-error').textContent='Connection lost. Keep the Vydra server terminal open. '+e.message}finally{polling=false}}
$('batch').addEventListener('invalid',()=>{if(!$('advanced').open)$('advanced').showModal()});
$('run-form').onsubmit=async event=>{event.preventDefault();if(submitting)return;submitting=true;render();$('form-error').textContent='';try{const run=await api('/api/runs',{mode:$('mode').value,input:$('source').value,output:$('output').value,device:$('device').value,model:$('model').value,offline:!$('offline').checked,report:$('report').checked,batch_size:$('batch').value||null});activeId=run.id;logShown=false;$('show-log').textContent='View execution log';$('execution-log').hidden=true;
 if(desktopRuns){runs=[run,...runs];$('source').value='';$('output').value='';desktopRuns.closeTask()}
 await poll()}catch(e){$('form-error').textContent=e.message}finally{submitting=false;render()}};
$('resume').onclick=async()=>{if(submitting)return;submitting=true;render();try{const run=await api('/api/resume/'+activeId,{});activeId=run.id;await poll()}catch(e){$('run-error').textContent=e.message}finally{submitting=false;render()}};
$('cancel').onclick=async()=>{try{await api('/api/cancel/'+activeId,{});await poll()}catch(e){$('run-error').textContent=e.message}};
$('show-log').onclick=async()=>{logShown=true;$('execution-log').hidden=false;$('log-dialog').showModal();try{const data=await api('/api/log/'+activeId);$('execution-log').textContent=data.log||'No log output yet.'}catch(e){$('execution-log').textContent=e.message}};
$('log-close').onclick=()=>$('log-dialog').close();$('log-dialog').onclose=()=>{logShown=false};
$('advanced-open').onclick=()=>$('advanced').showModal();$('advanced-close').onclick=()=>$('advanced').close();
$('faq-open').onclick=()=>$('faq-dialog').showModal();$('faq-close').onclick=()=>$('faq-dialog').close();
$('check').onclick=async()=>{$('check').disabled=true;$('check-log').hidden=false;$('check-log').textContent='Checking the installed Python environment, CUDA, models, and artifacts…';try{const result=await api('/api/check',{});$('check-log').textContent=(result.ok?'Installation is ready.\n':'Some requirements are missing.\n')+result.log}catch(e){$('check-log').textContent=e.message}finally{$('check').disabled=false}};
async function browse(path){$('browser-error').textContent='';try{const result=await api('/api/browse?path='+encodeURIComponent(path));$('browser-path').value=result.path;parentPath=result.parent;$('entries').replaceChildren();result.entries.forEach(entry=>{if(!entry.directory&&!(browseTarget==='source'&&$('mode').value==='file'))return;const button=document.createElement('button');button.type='button';button.textContent=(entry.directory?'Folder · ':'FASTA · ')+entry.name;button.onclick=()=>{if(entry.directory)browse(entry.path);else{$('source').value=entry.path;$('browser').close()}};$('entries').append(button)})}catch(e){$('browser-error').textContent=e.message}}
function openBrowser(target){if(!config)return;browseTarget=target;const files=target==='source'&&$('mode').value==='file';$('browser-title').textContent=target==='output'?'Choose results location':files?'Select protein FASTA file':'Select input folder';$('new-folder-label').hidden=target!=='output';$('choose-folder').hidden=files;$('choose-folder').textContent=target==='output'?'Use this results folder':'Select this folder';$('new-folder').value='vydra-run-'+new Date().toISOString().replace(/[:.]/g,'-');$('browser').showModal();browse(config.home)}
$('browse-source').onclick=()=>openBrowser('source');$('browse-output').onclick=()=>openBrowser('output');$('close-browser').onclick=()=>$('browser').close();$('go').onclick=()=>browse($('browser-path').value);$('browser-path').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();browse($('browser-path').value)}};$('up').onclick=()=>browse(parentPath);$('home').onclick=()=>browse(config.home);
$('choose-folder').onclick=()=>{let path=$('browser-path').value;if(browseTarget==='output'){const name=$('new-folder').value.trim();if(!name||/[\\/]/.test(name)||name==='.'||name==='..'){$('browser-error').textContent='Enter a new folder name without path separators.';return}path=path.replace(/[\\/]$/,'')+(path.includes('\\')?'\\':'/')+name}$(browseTarget==='output'?'output':'source').value=path;$('browser').close()};
const tips={"theme": "Switch between dark and light appearance. Your choice is saved in this browser.", "faq-open": "Read input requirements, execution guidance, and interpretation answers adapted from the documented FAQ.", "mode": "Choose one protein FASTA file, or search a folder and its subfolders for FASTA files.", "source": "Path to protein FASTA input. DNA and RNA must be translated before using Vydra.", "output": "Choose a new or empty output folder outside the input folder. Existing results are never overwritten.", "browse-source": "Browse local folders and protein FASTA files on the computer running Vydra.", "browse-output": "Choose a parent directory and name a new results folder.", "advanced-open": "Configure device, batch size, offline mode, and report generation.", "device": "Select the device for all inference: models and FAISS. Automatic uses a compatible GPU when available, otherwise CPU. Explicit GPU requires CUDA and GPU FAISS.", "batch": "Number of sequences embedded together. Leave empty for automatic sizing; smaller batches can reduce memory use.", "offline": "Always reuse local models first. If enabled, missing model files may be downloaded once and cached. Disable to require offline use. Proteins are processed locally.", "report": "Generate the interactive HTML inference report and supporting exports after predictions are saved.", "check": "Check the Python environment, CUDA, model files, and reference artifacts without running inference.", "start": "Start inference using these inputs and settings. Only one job runs at a time.", "show-log": "Open the execution log. It updates while the run is active.", "cancel": "Stop this run. Checkpoints are retained; select Resume run to reuse saved chunks and predictions.", "status-badge": "Current state of the selected run.", "status-text": "Current execution phase. Classification progress uses actual protein counts.", "processed": "Completed and remaining proteins in the current phase. During embedding generation, chunks show immediate model progress.", "elapsed": "Time since the selected run started.", "saved-output": "Location where this run saves its predictions and supporting files.", "progress": "Completed chunks during embedding generation; completed proteins during classification. This measures work in the current phase.", "recent": "Select a completed run to open its results report. Runs without a report show their status and log. History is stored locally.", "browser-path": "Enter a folder path on the computer running the Vydra server.", "go": "Open the folder at the entered path.", "up": "Open the parent of the current folder.", "home": "Open your home directory.", "new-folder": "Name the new results folder inside the selected parent directory.", "choose-folder": "Confirm the current input folder or new results location.", "close-browser": "Close the folder browser without changing your selection.", "advanced-close": "Close settings and keep your current choices.", "faq-close": "Return to the inference screen.", "log-close": "Close the log; inference continues in the background."};
const tooltip=document.createElement('div');tooltip.className='help-tip';tooltip.id='help-tooltip';tooltip.role='tooltip';tooltip.hidden=true;document.body.append(tooltip);
function hideTip(){tooltip.hidden=true}
function showTip(element){(element.closest('dialog')||document.body).append(tooltip);tooltip.textContent=element.dataset.help;tooltip.hidden=false;const rect=element.getBoundingClientRect();const width=tooltip.offsetWidth,height=tooltip.offsetHeight;tooltip.style.left=Math.max(12,Math.min(rect.left,innerWidth-width-12))+'px';tooltip.style.top=(rect.bottom+height+16<innerHeight?rect.bottom+8:Math.max(8,rect.top-height-8))+'px'}
Object.entries(tips).forEach(([id,tip])=>{const element=$(id);if(!element)return;element.dataset.help=tip;element.setAttribute('aria-description',tip);element.addEventListener('mouseenter',()=>showTip(element));element.addEventListener('mouseleave',hideTip);element.addEventListener('focus',()=>showTip(element));element.addEventListener('blur',hideTip);element.addEventListener('click',hideTip);const label=element.labels?.[0];if(label&&element.type==='checkbox'){label.dataset.help=tip;label.addEventListener('mouseenter',()=>showTip(label));label.addEventListener('mouseleave',hideTip)}});
window.addEventListener('resize',hideTip);document.addEventListener('keydown',e=>{if(e.key==='Escape')hideTip()});
function updateClassifier() {
  const selected = config.models.find(model => model.id === $('model').value);
  $('model-note').textContent = !selected?.faiss
    ? 'Install the FAISS M4 bank for this embedding model before starting.'
    : $('device').value === 'cpu'
    ? 'No comparable CPU speed measurements. Listed speeds are for the RTX 3060.'
    : 'Encoder speed on RTX 3060 at full batches, 75–1022 aa. Speed varies with length and hardware.';
}
$('model').onchange = updateClassifier;
$('device').onchange = updateClassifier;

(async()=>{try{config=await api('/api/config');
  $('model').replaceChildren(...config.models.map(model => {
    const option = new Option(`${model.name} · ${model.size} · ${model.speed}${model.installed?(model.faiss?'':' · M4 bank missing'):' · not installed'}`, model.id);
    option.disabled = !model.installed || !model.faiss;
    return option;
  }));
  const firstAvailable = [...$('model').options].find(option => !option.disabled);
  if (firstAvailable) $('model').value = firstAvailable.value;
  if (config.desktop) {
    desktopRuns=window.createVydraDesktopRuns({selectRun,showReport});
    desktopRuns.mount(config);
    $('start').dataset.help='Start a task or add it to the end of the queue.';
    $('start').setAttribute('aria-description', $('start').dataset.help);
    const device = $('device');
    const gpu = device.querySelector('option[value="cuda"]');
    gpu.textContent = config.desktop.windows ? 'NVIDIA (models) · CPU (FAISS)' : 'NVIDIA (models and FAISS)';
    gpu.disabled = config.desktop.mode === 'cpu';
    device.value = config.desktop.mode;
    const help = 'Select CPU or the NVIDIA mode prepared in Vydra Desktop.';
    device.dataset.help = help;
    device.setAttribute('aria-description', help);
    device.closest('dialog').querySelector('.hint').textContent = config.desktop.mode === 'cpu'
      ? 'This Vydra Desktop environment uses CPU. Close this window to prepare NVIDIA in the setup assistant.'
      : gpu.textContent + '. You can also select CPU for this run.';
    $('offline').checked = false;
    document.querySelector('footer').textContent = 'Keep Vydra Desktop open while an analysis is running.';
  }
  updateClassifier();
$('output').placeholder=config.home+'/vydra-results/new-run';await poll();setInterval(poll,1500)}catch(e){$('form-error').textContent=e.message}})();
})();
