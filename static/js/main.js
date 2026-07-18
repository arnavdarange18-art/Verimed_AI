// Handles Multimodal Fact Checker Forms
const checkerForm = document.getElementById('checkerForm');
if (checkerForm) {
    checkerForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(checkerForm);
        
        // Show loading progress state
        document.getElementById('resultsPlaceholder').classList.add('hidden');
        const resultsCard = document.getElementById('resultsCard');
        resultsCard.classList.remove('hidden');
        document.getElementById('verdictLabel').innerText = "Processing Pipeline... 🧬";
        document.getElementById('explanationText').innerText = "Extracting entities via BioBERT & checking RAG sources[cite: 1]...";

        try {
            const response = await fetch('/api/verify', { method: 'POST', body: formData });
            const data = await response.json();

            // Render Dynamic UI Updates based on response
            const badge = document.getElementById('verdictBadge');
            badge.className = `p-5 rounded-2xl border flex flex-col gap-2 verdict-${data.verdict.toLowerCase()}`;
            
            document.getElementById('verdictLabel').innerText = `Verdict: ${data.verdict}`;
            document.getElementById('explanationText').innerText = data.explanation;
            document.getElementById('confidenceValue').innerText = `${data.confidence}%`;
            document.getElementById('confidenceBar').style.width = `${data.confidence}%`;

            // Build Medical Entity Chips[cite: 1]
            const entityContainer = document.getElementById('entityContainer');
            entityContainer.innerHTML = data.entities.map(e => 
                `<span class="bg-blue-50 text-blue-700 text-[11px] font-bold px-2.5 py-1 rounded-full border border-blue-200">${e.text} &middot; ${e.label}</span>`
            ).join('');

            // Build Source Citation Chips[cite: 1]
            const sourceContainer = document.getElementById('sourceContainer');
            sourceContainer.innerHTML = data.sources.map(s => 
                `<span class="flex items-center gap-1.5"><i class="fa-solid fa-circle-check text-emerald-500 text-[10px]"></i> ${s}</span>`
            ).join('');

            // Fill Shareable Notice Card
            document.getElementById('shareVerdict').innerText = `🚨 MYTH CHECK: ${data.verdict}`;
            document.getElementById('shareExplanation').innerText = `"${data.explanation}"`;

        } catch (err) {
            console.error("Pipeline failure: ", err);
        }
    });
}

// Handles GNN Structural Virality Simulators[cite: 1]
async function runPredictionPipeline() {
    const claim = document.getElementById('predictInput').value;
    const panel = document.getElementById('predictOutputPanel');
    if (!claim) return alert("Please specify narrative terms.");

    panel.innerHTML = `<div class="m-auto text-xs font-bold animate-pulse text-purple-400"><i class="fa-solid fa-spinner fa-spin text-lg mr-2"></i>Executing topological structural edge learning evaluation matrices[cite: 1]...</div>`;

    const response = await fetch('/api/predict_spread', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ claim })
    });
    const data = await response.json();

    panel.innerHTML = `
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 text-center">
            <div class="bg-slate-800/60 p-4 rounded-xl border border-purple-900/40">
                <span class="text-[10px] text-purple-400 uppercase font-bold tracking-wider">Virality Risk Score[cite: 1]</span>
                <h4 class="text-2xl font-black text-purple-400 mt-1">${data.virality_score}%</h4>
            </div>
            <div class="bg-slate-800/60 p-4 rounded-xl border border-purple-900/40">
                <span class="text-[10px] text-purple-400 uppercase font-bold tracking-wider">Node Critical Level[cite: 1]</span>
                <h4 class="text-2xl font-black text-red-400 mt-1">${data.risk_level}</h4>
            </div>
            <div class="bg-slate-800/60 p-4 rounded-xl border border-purple-900/40">
                <span class="text-[10px] text-purple-400 uppercase font-bold tracking-wider">Peak Horizon Reach[cite: 1]</span>
                <h4 class="text-2xl font-black text-cyan-400 mt-1">${data.time_to_peak_hours} Hours</h4>
            </div>
        </div>
        <div class="bg-slate-800/40 p-4 rounded-xl border border-slate-800">
            <span class="text-[10px] uppercase text-slate-400 font-bold block mb-2">High-Risk Hub Vulnerability Map</span>
            <ul class="text-xs text-slate-300 flex flex-col gap-1.5">
                ${data.network_hubs_vulnerable.map(h => `<li><i class="fa-solid fa-triangle-exclamation text-amber-500 mr-2"></i> At Risk: <b>${h}</b></li>`).join('')}
            </ul>
        </div>
    `;
}

// File Input Name Decorator
const imgInput = document.getElementById('imageInput');
if (imgInput) {
    imgInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) document.getElementById('fileName').innerText = `Selected File: ${file.name} (OCR Ready)[cite: 1]`;
    });
}