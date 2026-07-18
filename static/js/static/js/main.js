// VeriMed AI -- frontend logic
// Wires the checker, predictor, and passport pages to the Flask API.

// ---------- Helpers ----------

function verdictColorClasses(verdict) {
    switch ((verdict || "").toLowerCase()) {
        case "true":
            return { badge: "bg-emerald-50 border-emerald-200 text-emerald-700", bar: "bg-emerald-600" };
        case "false":
            return { badge: "bg-red-50 border-red-200 text-red-700", bar: "bg-red-600" };
        case "misleading":
            return { badge: "bg-amber-50 border-amber-200 text-amber-700", bar: "bg-amber-600" };
        default:
            return { badge: "bg-slate-50 border-slate-200 text-slate-700", bar: "bg-slate-500" };
    }
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
}

// ---------- Checker page ----------

const checkerForm = document.getElementById("checkerForm");
if (checkerForm) {
    const imageInput = document.getElementById("imageInput");
    const fileNameLabel = document.getElementById("fileName");

    if (imageInput) {
        imageInput.addEventListener("change", () => {
            if (imageInput.files.length > 0) {
                fileNameLabel.textContent = `Selected: ${imageInput.files[0].name}`;
            }
        });
    }

    checkerForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const submitBtn = checkerForm.querySelector("button[type='submit']");
        const originalBtnHtml = submitBtn.innerHTML;
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Analyzing...`;

        const placeholder = document.getElementById("resultsPlaceholder");
        const resultsCard = document.getElementById("resultsCard");

        try {
            const formData = new FormData(checkerForm);
            const res = await fetch("/api/verify", { method: "POST", body: formData });
            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.explanation || data.error || "Verification failed.");
            }

            renderCheckerResult(data);
            placeholder.classList.add("hidden");
            resultsCard.classList.remove("hidden");
        } catch (err) {
            placeholder.classList.remove("hidden");
            resultsCard.classList.add("hidden");
            placeholder.innerHTML = `
                <i class="fa-solid fa-triangle-exclamation text-4xl mb-3 text-red-400"></i>
                <p class="font-bold text-sm text-red-500">${escapeHtml(err.message)}</p>
            `;
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalBtnHtml;
        }
    });
}

function renderCheckerResult(data) {
    const colors = verdictColorClasses(data.verdict);

    const verdictBadge = document.getElementById("verdictBadge");
    verdictBadge.className = `p-5 rounded-2xl border flex flex-col gap-2 ${colors.badge}`;
    document.getElementById("verdictLabel").textContent = data.verdict || "Unverified";
    document.getElementById("explanationText").textContent = data.explanation || "";

    const confidence = Number(data.confidence) || 0;
    document.getElementById("confidenceValue").textContent = `${confidence}%`;
    const bar = document.getElementById("confidenceBar");
    bar.style.width = `${confidence}%`;
    bar.className = `h-full transition-all duration-500 ${colors.bar}`;

    const entityContainer = document.getElementById("entityContainer");
    entityContainer.innerHTML = "";
    (data.entities || []).forEach((ent) => {
        const chip = document.createElement("span");
        chip.className = "text-[11px] font-bold bg-blue-50 text-blue-700 px-2.5 py-1 rounded-full border border-blue-100";
        chip.textContent = `${ent.text} · ${ent.label}`;
        entityContainer.appendChild(chip);
    });
    if (!data.entities || data.entities.length === 0) {
        entityContainer.innerHTML = `<span class="text-xs text-slate-400">No entities detected.</span>`;
    }

    const sourceContainer = document.getElementById("sourceContainer");
    sourceContainer.innerHTML = "";
    (data.sources || []).forEach((src) => {
        const line = document.createElement("div");
        line.innerHTML = `<i class="fa-solid fa-check text-emerald-500 mr-1"></i> ${escapeHtml(src)}`;
        sourceContainer.appendChild(line);
    });
    if (!data.sources || data.sources.length === 0) {
        sourceContainer.innerHTML = `<span class="text-xs text-slate-400">No sources returned.</span>`;
    }

    document.getElementById("shareVerdict").textContent = `Verdict: ${data.verdict || "Unverified"}`;
    document.getElementById("shareExplanation").textContent = data.explanation || "";
}

// ---------- Predictor page ----------

async function runPredictionPipeline() {
    const input = document.getElementById("predictInput");
    const panel = document.getElementById("predictOutputPanel");
    const claim = input.value.trim();

    if (!claim) {
        panel.innerHTML = `<div class="m-auto text-center text-amber-400 font-bold text-xs">Enter a claim first.</div>`;
        return;
    }

    panel.innerHTML = `
        <div class="m-auto text-center text-slate-500 font-bold text-xs flex flex-col gap-2 items-center">
            <i class="fa-solid fa-circle-nodes text-3xl text-purple-500/50 animate-spin"></i>
            Running network spread simulation...
        </div>
    `;

    try {
        const res = await fetch("/api/predict_spread", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ claim }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Prediction failed.");

        const riskColor = data.risk_level === "High Risk" ? "text-red-400" : "text-emerald-400";
        panel.innerHTML = `
            ${data.is_simulated ? `<div class="text-[10px] uppercase tracking-wider font-bold text-amber-400 mb-1">
                <i class="fa-solid fa-flask mr-1"></i> Simulated placeholder -- GNN model not yet trained
            </div>` : ""}
            <div class="grid grid-cols-2 gap-4">
                <div class="bg-slate-800/60 rounded-xl p-4">
                    <span class="text-[10px] uppercase font-bold text-slate-400">Virality Score</span>
                    <div class="text-3xl font-black mt-1">${escapeHtml(data.virality_score)}</div>
                </div>
                <div class="bg-slate-800/60 rounded-xl p-4">
                    <span class="text-[10px] uppercase font-bold text-slate-400">Risk Level</span>
                    <div class="text-xl font-black mt-1 ${riskColor}">${escapeHtml(data.risk_level)}</div>
                </div>
                <div class="bg-slate-800/60 rounded-xl p-4">
                    <span class="text-[10px] uppercase font-bold text-slate-400">Predicted Nodes Reached</span>
                    <div class="text-2xl font-black mt-1">${escapeHtml(data.predicted_nodes_reached)}</div>
                </div>
                <div class="bg-slate-800/60 rounded-xl p-4">
                    <span class="text-[10px] uppercase font-bold text-slate-400">Time To Peak</span>
                    <div class="text-2xl font-black mt-1">${escapeHtml(data.time_to_peak_hours)}h</div>
                </div>
            </div>
            <div class="bg-slate-800/60 rounded-xl p-4">
                <span class="text-[10px] uppercase font-bold text-slate-400 block mb-2">Vulnerable Network Hubs</span>
                <div class="flex flex-wrap gap-2">
                    ${(data.network_hubs_vulnerable || []).map(h => `<span class="text-[11px] font-bold bg-purple-500/10 text-purple-300 px-2.5 py-1 rounded-full border border-purple-500/20">${escapeHtml(h)}</span>`).join("")}
                </div>
            </div>
        `;
    } catch (err) {
        panel.innerHTML = `<div class="m-auto text-center text-red-400 font-bold text-xs">${escapeHtml(err.message)}</div>`;
    }
}

// ---------- Passport page ----------

const passportForm = document.getElementById("passportForm");
if (passportForm) {
    // Load any existing saved passport on page load
    fetch("/api/passport")
        .then((res) => res.json())
        .then((data) => {
            if (!data) return;
            document.getElementById("passName").value = data.full_name || "";
            document.getElementById("passBlood").value = data.blood_group || "";
            document.getElementById("passAllergies").value = data.allergies || "";
            document.getElementById("passMeds").value = data.current_medicines || "";
            document.getElementById("passContact").value = data.emergency_contact_name || "";
            document.getElementById("passPhone").value = data.emergency_contact_phone || "";
            showQrCode();
        })
        .catch(() => {});

    passportForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const payload = {
            full_name: document.getElementById("passName").value,
            blood_group: document.getElementById("passBlood").value,
            date_of_birth: "",
            allergies: document.getElementById("passAllergies").value,
            chronic_conditions: "",
            current_medicines: document.getElementById("passMeds").value,
            emergency_contact_name: document.getElementById("passContact").value,
            emergency_contact_phone: document.getElementById("passPhone").value,
        };

        const submitBtn = passportForm.querySelector("button[type='submit']");
        const originalText = submitBtn.textContent;
        submitBtn.disabled = true;
        submitBtn.textContent = "Saving...";

        try {
            const res = await fetch("/api/passport", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            if (!res.ok) throw new Error("Failed to save passport.");
            showQrCode();
        } catch (err) {
            alert(err.message);
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
        }
    });
}

function showQrCode() {
    const qrContainer = document.getElementById("qrContainer");
    if (!qrContainer) return;
    // Cache-bust so the browser doesn't show a stale QR after an update
    qrContainer.innerHTML = `<img src="/api/passport/qr?t=${Date.now()}" alt="Health Passport QR Code" class="w-40 h-40 object-contain" />`;
}
