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

    // ---- Voice-to-text (Web Speech API -- browser-native, no API key) ----
    const voiceBtn = document.getElementById("voiceInputBtn");
    const voiceLabel = document.getElementById("voiceInputLabel");
    const claimTextarea = document.getElementById("claimTextarea");
    const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (voiceBtn && SpeechRecognitionAPI) {
        const recognition = new SpeechRecognitionAPI();
        recognition.continuous = false;
        recognition.interimResults = false;

        voiceBtn.addEventListener("click", () => {
            const langSelect = checkerForm.querySelector("select[name='language']");
            recognition.lang = langSelect ? langSelect.value : "en-US";
            recognition.start();
            voiceBtn.classList.add("text-red-600");
            voiceLabel.textContent = "Listening...";
        });

        recognition.addEventListener("result", (event) => {
            const transcript = event.results[0][0].transcript;
            claimTextarea.value = (claimTextarea.value ? claimTextarea.value + " " : "") + transcript;
        });

        recognition.addEventListener("end", () => {
            voiceBtn.classList.remove("text-red-600");
            voiceLabel.textContent = "Speak";
        });

        recognition.addEventListener("error", () => {
            voiceBtn.classList.remove("text-red-600");
            voiceLabel.textContent = "Speak";
        });
    } else if (voiceBtn) {
        // Browser doesn't support Speech Recognition (e.g. Firefox) -- hide gracefully
        voiceBtn.style.display = "none";
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

    // If the claim came from an uploaded screenshot, show the OCR'd text so
    // the user can confirm it was read correctly before trusting the verdict.
    let ocrNote = "";
    const existingOcrNote = document.getElementById("ocrExtractedNote");
    if (existingOcrNote) existingOcrNote.remove();
    if (data.ocr_used && data.claim_text_used) {
        ocrNote = document.createElement("div");
        ocrNote.id = "ocrExtractedNote";
        ocrNote.className = "text-[11px] font-semibold text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 mb-1";
        ocrNote.innerHTML = `<i class="fa-solid fa-text-height mr-1"></i> Text read from image: "${escapeHtml(data.claim_text_used)}"`;
        verdictBadge.parentElement.insertBefore(ocrNote, verdictBadge);
    }

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

    // ---- Text-to-speech: read the verdict + explanation aloud ----
    const speakBtn = document.getElementById("speakResultBtn");
    const speakLabel = document.getElementById("speakResultLabel");
    if (speakBtn && "speechSynthesis" in window) {
        speakBtn.onclick = () => {
            window.speechSynthesis.cancel(); // stop any previous playback
            const utterance = new SpeechSynthesisUtterance(
                `Verdict: ${data.verdict}. ${data.explanation || ""}`
            );
            utterance.rate = 0.95;
            utterance.onstart = () => { speakLabel.textContent = "Stop"; };
            utterance.onend = () => { speakLabel.textContent = "Listen"; };
            window.speechSynthesis.speak(utterance);
        };
    } else if (speakBtn) {
        speakBtn.style.display = "none";
    }
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
            Computing spread risk signals...
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

        const riskColor = data.risk_level === "High Risk" ? "text-red-400" : (data.risk_level === "Medium Risk" ? "text-amber-400" : "text-emerald-400");
        const breakdown = data.signal_breakdown || {};

        panel.innerHTML = `
            <div class="text-[10px] uppercase tracking-wider font-bold text-blue-400 mb-1 flex items-center gap-1.5">
                <i class="fa-solid fa-diagram-project"></i> Heuristic graph + language analysis -- not a trained model
            </div>
            <div class="grid grid-cols-2 gap-4">
                <div class="bg-slate-800/60 rounded-xl p-4">
                    <span class="text-[10px] uppercase font-bold text-slate-400">Risk Score</span>
                    <div class="text-3xl font-black mt-1">${escapeHtml(data.virality_score)}<span class="text-sm text-slate-500">/100</span></div>
                </div>
                <div class="bg-slate-800/60 rounded-xl p-4">
                    <span class="text-[10px] uppercase font-bold text-slate-400">Risk Level</span>
                    <div class="text-xl font-black mt-1 ${riskColor}">${escapeHtml(data.risk_level)}</div>
                </div>
                <div class="bg-slate-800/60 rounded-xl p-4">
                    <span class="text-[10px] uppercase font-bold text-slate-400">Estimated Reach (order of magnitude)</span>
                    <div class="text-xl font-black mt-1">${escapeHtml(data.reach_estimate_bucket)}</div>
                </div>
                <div class="bg-slate-800/60 rounded-xl p-4">
                    <span class="text-[10px] uppercase font-bold text-slate-400">Est. Time To Peak</span>
                    <div class="text-2xl font-black mt-1">${escapeHtml(data.time_to_peak_hours)}h</div>
                </div>
            </div>
            <div class="bg-slate-800/60 rounded-xl p-4">
                <span class="text-[10px] uppercase font-bold text-slate-400 block mb-2">Signal Breakdown</span>
                <div class="flex flex-col gap-2 text-xs">
                    <div class="flex justify-between"><span class="text-slate-300">Matches known misinformation pattern</span><span class="font-bold">${escapeHtml(breakdown.misinformation_pattern_match ?? "-")}</span></div>
                    <div class="flex justify-between"><span class="text-slate-300">Sensational language score</span><span class="font-bold">${escapeHtml(breakdown.sensational_language_score ?? "-")}</span></div>
                    <div class="flex justify-between"><span class="text-slate-300">Entity graph embeddedness</span><span class="font-bold">${escapeHtml(breakdown.entity_embeddedness_score ?? "-")}</span></div>
                </div>
            </div>
            <div class="text-[10px] text-slate-500 leading-relaxed px-1">
                ${escapeHtml(data.methodology || "")}
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

// ---------- Home page: Personalized Snapshot ----------

const passportSnapshotCard = document.getElementById("passportSnapshotCard");
if (passportSnapshotCard) {
    fetch("/api/passport")
        .then((res) => res.json())
        .then((data) => {
            const emptyState = document.getElementById("passportSnapshotEmpty");
            const snapshotCard = document.getElementById("passportSnapshotCard");
            const qrCard = document.getElementById("passportSnapshotQr");

            if (!data || !data.full_name) {
                emptyState.classList.remove("hidden");
                return;
            }

            document.getElementById("snapName").textContent = data.full_name || "--";
            document.getElementById("snapBlood").textContent = data.blood_group || "--";
            document.getElementById("snapAllergies").textContent = data.allergies || "None listed";
            document.getElementById("snapMeds").textContent = data.current_medicines || "None listed";

            const snapQrContainer = document.getElementById("snapQrContainer");
            snapQrContainer.innerHTML = `<img src="/api/passport/qr?t=${Date.now()}" alt="Emergency QR" class="w-28 h-28 object-contain" />`;

            snapshotCard.classList.remove("hidden");
            qrCard.classList.remove("hidden");
        })
        .catch(() => {
            document.getElementById("passportSnapshotEmpty").classList.remove("hidden");
        });
}

// ---------- Home page: Trending Misinformation ----------

const trendingContainer = document.getElementById("trendingContainer");
if (trendingContainer) {
    fetch("/api/trending?limit=5")
        .then((res) => res.json())
        .then((trending) => {
            if (!trending || trending.length === 0) {
                trendingContainer.innerHTML = `<div class="text-center text-slate-400 text-sm py-6">No trends yet -- check a few claims to build history.</div>`;
                return;
            }

            trendingContainer.innerHTML = trending.map((t) => {
                const colors = verdictColorClasses(t.verdict);
                return `
                    <div class="bg-white p-4 rounded-xl border ${colors.badge} flex items-center justify-between gap-4">
                        <div class="flex items-center gap-3 min-w-0">
                            <span class="text-[10px] font-black uppercase px-2 py-1 rounded-full ${colors.badge} shrink-0">${escapeHtml(t.verdict || "Unverified")}</span>
                            <p class="text-sm font-semibold text-slate-700 truncate">"${escapeHtml(t.claim_text || "")}"</p>
                        </div>
                        <span class="text-xs font-bold text-slate-400 shrink-0">${escapeHtml(t.check_count)}x checked</span>
                    </div>`;
            }).join("");
        })
        .catch(() => {
            trendingContainer.innerHTML = `<div class="text-center text-red-400 text-sm py-6">Couldn't load trending data.</div>`;
        });
}

// ---------- Home page: Latest Health Alerts (live from history) ----------

const latestAlertsContainer = document.getElementById("latestAlertsContainer");
if (latestAlertsContainer) {
    fetch("/api/history?limit=3")
        .then((res) => res.json())
        .then((history) => {
            if (!history || history.length === 0) {
                latestAlertsContainer.innerHTML = `
                    <div class="md:col-span-3 text-center text-slate-400 text-sm py-6">
                        No claims checked yet. <a href="/checker" class="text-blue-600 font-bold hover:underline">Check your first claim &rarr;</a>
                    </div>`;
                return;
            }

            latestAlertsContainer.innerHTML = history.map((h) => {
                const colors = verdictColorClasses(h.verdict);
                return `
                    <div class="bg-white p-5 border rounded-2xl shadow-sm ${colors.badge}">
                        <span class="text-xs font-black uppercase tracking-wide">${escapeHtml(h.verdict || "Unverified")}</span>
                        <p class="text-sm font-bold text-slate-800 mt-2 leading-snug">"${escapeHtml((h.claim_text || "").slice(0, 90))}${(h.claim_text || "").length > 90 ? "..." : ""}"</p>
                        <p class="text-xs text-slate-400 mt-2">${escapeHtml(h.timestamp || "")}</p>
                    </div>`;
            }).join("");
        })
        .catch(() => {
            latestAlertsContainer.innerHTML = `<div class="md:col-span-3 text-center text-red-400 text-sm py-6">Couldn't load recent alerts.</div>`;
        });
}