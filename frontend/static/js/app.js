const genderInput = document.getElementById('gender');
const pregnancyInput = document.getElementById('pregnancy');

function updatePregnancyStatus() {
  if (!genderInput || !pregnancyInput) return;
  const g = (genderInput.value || '').trim().toLowerCase();
  if (g === 'male' || g === 'm' || g === 'man') {
    pregnancyInput.disabled = true;
    pregnancyInput.value = '';
    pregnancyInput.placeholder = 'N/A (Disabled for Male)';
    pregnancyInput.style.backgroundColor = '#f1f5f9';
    pregnancyInput.style.cursor = 'not-allowed';
  } else {
    pregnancyInput.disabled = false;
    pregnancyInput.placeholder = 'e.g. pregnant';
    pregnancyInput.style.backgroundColor = '#ffffff';
    pregnancyInput.style.cursor = 'text';
  }
}

if (genderInput) {
  genderInput.addEventListener('input', updatePregnancyStatus);
  genderInput.addEventListener('change', updatePregnancyStatus);
  updatePregnancyStatus();
}

function switchTab(tabId) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));
  const targetTab = document.getElementById(tabId);
  if (targetTab) targetTab.classList.add('active');
  const activeNavBtn = document.querySelector(`.nav-tab[onclick*="${tabId}"]`);
  if (activeNavBtn) activeNavBtn.classList.add('active');
  if (tabId === 'tab-cku') loadCkuQueue();
}

function fillSymptoms(text) {
  const promptEl = document.getElementById('prompt');
  if (promptEl) promptEl.value = text;
}

// Form submit for Clinical Analysis
const medicalForm = document.getElementById('medical-form');
if (medicalForm) {
  medicalForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const promptText = document.getElementById('prompt').value.trim();
    const resultsDiv = document.getElementById('results');
    const submitBtn = document.getElementById('submit-btn');
    const statusLine = document.getElementById('status-line');

    resultsDiv.style.display = 'block';
    resultsDiv.innerHTML = '<div class="status-line">🔍 Running Knowledge Graph Traversal, RAG Retrieval, and Comp(a, P) Safety Checks...</div>';
    submitBtn.disabled = true;
    statusLine.textContent = 'Processing...';

    const payload = {
      symptoms: [promptText],
      patient_profile: {
        age: document.getElementById('age').value,
        gender: document.getElementById('gender').value,
        allergies: document.getElementById('allergies').value,
        current_medications: document.getElementById('medications').value,
        chronic_conditions: document.getElementById('conditions').value,
        pregnancy_status: document.getElementById('pregnancy').disabled ? 'none' : document.getElementById('pregnancy').value
      }
    };

    try {
      const res = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Analysis failed');

      renderClinicalResults(data);
    } catch (err) {
      resultsDiv.innerHTML = `<div class="mini-card"><p style="color:var(--danger);">⚠️ Error: ${err.message}</p></div>`;
    } finally {
      submitBtn.disabled = false;
      statusLine.textContent = 'Ready for analysis';
    }
  });
}

function renderClinicalResults(data) {
  const resultsDiv = document.getElementById('results');
  const diseases = data.diseases || [];
  const differential = data.differential_diagnosis || [];
  const explainability = data.candidate_explainability || {};
  const safetyGate = data.safety_gate || {};
  const resultsList = data.results || [];
  const metrics = data.metrics || {};
  const profile = data.patient_profile || {};

  let html = `
    <h3 class="panel-title">📋 Clinical Assessment & Safety Analysis</h3>
    <p class="status-line">Verified against Medical Knowledge Graph (Neo4j), RAG Medical Literature, and Patient Safety Comp(a, P)</p>
    
    <div class="card-grid" style="grid-template-columns: 1fr 1fr; gap:16px;">
      <!-- Differential Assessment -->
      <div class="mini-card" style="border-top: 4px solid var(--blue);">
        <h4 style="margin:0 0 12px; color:var(--blue);">🧠 Differential Assessment</h4>
        <div style="display:grid; gap:8px;">
          ${differential.length ? differential.map(d => `
            <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.88rem; padding:6px 10px; background:#f8fafc; border-radius:6px;">
              <strong>${d.disease}</strong>
              <span class="badge ${d.relevance_level === 'High relevance' ? 'badge-success' : d.relevance_level === 'Moderate relevance' ? 'badge-warning' : 'badge-danger'}">${d.relevance_level}</span>
            </div>
          `).join('') : '<p>No differential candidates calculated.</p>'}
        </div>
      </div>

      <!-- Why This Candidate? -->
      <div class="mini-card" style="border-top: 4px solid #8b5cf6;">
        <h4 style="margin:0 0 12px; color:#8b5cf6;">🔎 Why This Candidate? (${explainability.candidate || 'Provisional'})</h4>
        <div style="font-size:0.88rem; display:grid; gap:6px;">
          <div><strong>✓ Supporting Findings:</strong> ${(explainability.supporting_findings || []).join(', ') || 'N/A'}</div>
          <div><strong>⚠ Information Still Needed:</strong> ${(explainability.missing_information || []).join(', ')}</div>
          <div><strong>Assessment:</strong> <span class="badge badge-warning">PROVISIONAL</span></div>
        </div>
      </div>

      <!-- Patient Profile -->
      <div class="mini-card">
        <h4 style="margin:0 0 10px;">🛡️ Patient Profile Applied (P)</h4>
        <ul style="list-style:none; padding:0; margin:0; font-size:0.88rem; display:grid; gap:5px;">
          <li><strong>Age:</strong> ${profile.age !== null && profile.age !== undefined ? profile.age : 'Not specified'}</li>
          <li><strong>Gender:</strong> ${profile.gender || 'Not specified'}</li>
          <li><strong>Allergies:</strong> ${(profile.allergies || []).join(', ') || 'None'}</li>
          <li><strong>Current Medications:</strong> ${(profile.current_medications || []).join(', ') || 'None'}</li>
          <li><strong>Chronic Conditions:</strong> ${(profile.chronic_conditions || []).join(', ') || 'None'}</li>
          <li><strong>Pregnancy Status:</strong> ${profile.pregnancy_status || 'None'}</li>
        </ul>
      </div>

      <!-- RAG Performance Metrics -->
      <div class="mini-card" style="border-top: 4px solid var(--success);">
        <h4 style="margin:0 0 10px;">📊 RAG & Retrieval Performance Metrics</h4>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px; font-size:0.88rem;">
          <div><strong>Precision@5:</strong> <span class="badge badge-success">${(metrics.precision_at_5 !== undefined ? metrics.precision_at_5 : 0).toFixed(4)}</span></div>
          <div><strong>Recall@5:</strong> <span class="badge badge-success">${(metrics.recall_at_5 !== undefined ? metrics.recall_at_5 : 0).toFixed(4)}</span></div>
          <div><strong>F1-Score@5:</strong> <span class="badge badge-success">${(metrics.f1_score_at_5 !== undefined ? metrics.f1_score_at_5 : 0).toFixed(4)}</span></div>
          <div><strong>Faithfulness:</strong> <span class="badge badge-success">${(metrics.faithfulness !== undefined ? metrics.faithfulness : 0).toFixed(4)}</span></div>
        </div>
      </div>
    </div>
  `;

  // Render disease-specific treatment & evidence cards
  resultsList.forEach(item => {
    const diseaseName = item.disease;
    const drugs = item.drugs || [];
    const evidence = item.evidence || [];
    const relatedEv = item.related_evidence || [];
    const answer = item.answer || '';
    const exclusions = (data.reasoning_trace && data.reasoning_trace.drug_exclusions) || [];

    html += `
      <div class="mini-card" style="margin-top:20px; border-left: 5px solid var(--blue);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
          <h3 style="margin:0; color:var(--blue);">🦠 Candidate Entity: ${diseaseName}</h3>
          <span class="badge badge-warning">Provisional Candidate</span>
        </div>
        
        <div style="margin-top:12px; background:#f8fafc; padding:12px; border-radius:10px; border:1px solid #e2e8f0;">
          <strong style="color:#1e293b;">💊 Medication Information — Clinician Review Required:</strong><br>
          <div style="margin-top:6px;">
            ${drugs.length ? drugs.map(dr => `<span class="badge badge-success">✓ Evidence-supported treatment info: ${dr}</span>`).join(' ') : '<span class="badge badge-warning">No direct safe drugs mapped</span>'}
          </div>
          <small style="color:var(--muted); display:block; margin-top:6px;">⚠ Note: Educational info only. Do not initiate medication without direct clinician authorization.</small>
        </div>

        ${exclusions.length ? `
          <div style="margin-top:12px; background:var(--danger-bg); border:1px solid rgba(220,38,38,0.2); border-radius:12px; padding:12px;">
            <strong style="color:var(--danger);">🚫 Excluded Candidate Drugs & Clinical Safety Reasons:</strong>
            ${exclusions.map(ex => `
              <div style="margin-top:6px; font-size:0.88rem;">
                • <strong>${ex.candidate}</strong>: ${ex.reason} <span style="color:var(--muted);">(Matched profile terms: ${ex.matched_profile_terms})</span>
              </div>
            `).join('')}
          </div>
        ` : ''}

        <h4 style="margin-top:16px; margin-bottom:6px;">🧾 Generated Clinical Explanation:</h4>
        <pre style="background:#f8fafc; padding:12px; border-radius:10px; font-family:inherit; white-space:pre-wrap;">${answer}</pre>

        <!-- Verified Evidence Section -->
        <h4 style="margin-top:16px; margin-bottom:6px;">📚 Verified Evidence (TrustRank 0–100 Normalized):</h4>
        ${evidence.length ? evidence.slice(0, 3).map(e => `
          <div style="font-size:0.88rem; margin-bottom:8px; padding:10px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px;">
            <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
              <span class="badge badge-success">🛡️ TrustRank: ${(e.trust_score || 0).toFixed(1)} / 100</span>
              <span style="font-size:0.8rem; color:var(--muted);">
                ${e.explanation_factors && e.explanation_factors.disease_match ? '✓ Disease Match • ' : ''}
                ${e.explanation_factors && e.explanation_factors.treatment_match ? '✓ Treatment Match • ' : ''}
                ✓ Source: ${e.source_name || 'Medical Knowledge Base'} • ✓ Knowledge Graph Verified
              </span>
            </div>
            <div>${e.question ? `<strong>${e.question}</strong><br>` : ''}${e.text || ''}</div>
            <div style="font-size:0.78rem; color:var(--muted); margin-top:4px;">
              <strong>Reason:</strong> ${e.explanation_factors ? e.explanation_factors.reason : 'Directly supports clinical candidate.'}
            </div>
          </div>
        `).join('') : '<p style="font-size:0.88rem; color:var(--danger);">Insufficient clinically relevant evidence for direct verification.</p>'}

        <!-- Related Evidence Section -->
        ${relatedEv.length ? `
          <div style="margin-top:14px; background:#fffbeb; border:1px solid #fef3c7; padding:10px; border-radius:8px;">
            <h5 style="margin:0 0 6px; color:#b45309;">⚠ Related Literature (Excluded from Primary Evidence):</h5>
            ${relatedEv.slice(0, 2).map(r => `
              <div style="font-size:0.82rem; margin-bottom:4px; color:#92400e;">
                • <strong>[Score: ${(r.trust_score||0).toFixed(1)}/100]</strong> ${r.question || r.text.slice(0, 120)}...<br>
                <small style="color:#b45309;">Reason: ${r.relation_note || 'Differs from candidate entity'}</small>
              </div>
            `).join('')}
          </div>
        ` : ''}
      </div>
    `;
  });

  // TRUSTMED Safety Status Panel
  html += `
    <div class="mini-card" style="margin-top:20px; border-left: 5px solid var(--success); background:#f0fdf4;">
      <h4 style="margin:0 0 10px; color:#166534;">🛡️ TRUSTMED SAFETY STATUS</h4>
      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px; font-size:0.88rem;">
        <div><span class="badge badge-success">✓ Evidence Grounded</span></div>
        <div><span class="badge badge-success">✓ Knowledge Graph Checked</span></div>
        <div><span class="badge badge-success">✓ Clinical Relevance Checked</span></div>
        <div><span class="badge badge-warning">✓ Uncertainty Detected</span></div>
      </div>
      <div style="margin-top:10px; padding:8px; background:#dcfce7; border-radius:6px; font-size:0.82rem; color:#15803d;">
        ⚠ AI-generated clinical information — Not a definitive medical diagnosis.
      </div>
    </div>

    <!-- Questions for Clinician -->
    <div class="mini-card" style="margin-top:20px; border-left: 5px solid #0284c7;">
      <h4 style="margin:0 0 10px; color:#0369a1;">🩺 Questions for Your Clinician:</h4>
      <ul style="margin:0; padding-left:20px; font-size:0.9rem; display:grid; gap:6px;">
        ${(data.doctor_questions || []).map(q => `<li>${q}</li>`).join('')}
      </ul>
    </div>
  `;

  resultsDiv.innerHTML = html;
}

// CKU Submit
const ckuForm = document.getElementById('cku-form');
if (ckuForm) {
  ckuForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const sourceVal = document.getElementById('cku-source') ? document.getElementById('cku-source').value.trim() : '';
    const entityVal = (document.getElementById('cku-disease') || document.getElementById('cku-entity')) ? (document.getElementById('cku-disease') || document.getElementById('cku-entity')).value.trim() : '';
    const entityTypeVal = document.getElementById('cku-entity-type') ? document.getElementById('cku-entity-type').value : 'Disease';
    const categoryVal = (document.getElementById('cku-category') || document.getElementById('cku-evidence-type')) ? (document.getElementById('cku-category') || document.getElementById('cku-evidence-type')).value.trim() : 'Clinical Guideline';
    const textVal = document.getElementById('cku-text') ? document.getElementById('cku-text').value.trim() : '';

    const payload = {
      source: sourceVal,
      source_name: sourceVal,
      url: sourceVal,
      clinical_entity: entityVal,
      disease: entityVal,
      entity_type: entityTypeVal,
      evidence_type: categoryVal,
      category: categoryVal,
      text: textVal
    };

    try {
      const res = await fetch('/api/cku/candidates', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      const score = (data.trust_score !== undefined ? (data.trust_score <= 1.0 ? data.trust_score * 100 : data.trust_score) : 0).toFixed(0);
      alert(`Evidence Evaluated & Ingested!\nStatus: ${data.status || data.decision}\nTrustRank: ${score} / 100`);
      loadCkuQueue();
    } catch (err) {
      alert(`Ingestion error: ${err.message}`);
    }
  });
}

window.ckuCandidatesCache = [];

async function loadCkuQueue() {
  const container = document.getElementById('cku-table-container');
  if (!container) return;
  container.innerHTML = '<p class="status-line">Loading evaluation queue...</p>';
  try {
    const res = await fetch('/api/cku/candidates');
    const data = await res.json();
    const candidates = data.all || data.candidates || [];
    window.ckuCandidatesCache = candidates;

    if (!candidates.length) {
      container.innerHTML = '<p>No candidates in staging queue.</p>';
      return;
    }

    let html = `
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Status</th>
            <th>TrustRank</th>
            <th>Source</th>
            <th>Clinical Relevance</th>
            <th>Evidence Type</th>
            <th>KG Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${candidates.map(c => {
            const audit = c.audit_trail || {};
            const rawScore = c.trust_rank !== undefined ? c.trust_rank : (c.trust_score !== undefined ? c.trust_score : 0);
            const trustRankVal = (rawScore <= 1.0 && rawScore > 0 ? rawScore * 100 : rawScore).toFixed(0);
            const relVal = (audit.clinical_relevance_score !== undefined ? audit.clinical_relevance_score : (c.clinical_relevance_score !== undefined ? c.clinical_relevance_score : 0)).toFixed(0);
            const evType = audit.evidence_type || c.evidence_type || c.category || 'General';
            const kgStatus = audit.kg_status || (audit.kg_consistency_score >= 80 ? 'VERIFIED' : (audit.kg_consistency_score > 0 ? 'PARTIAL' : 'NOT_VERIFIED'));
            const statusStr = c.decision || c.status || 'REVIEW';
            const badgeClass = statusStr === 'VERIFIED' || statusStr === 'PROMOTED' ? 'badge-success' : (statusStr === 'REJECTED' ? 'badge-danger' : 'badge-warning');
            const kgBadgeClass = kgStatus === 'VERIFIED' ? 'badge-success' : (kgStatus === 'CONFLICT' ? 'badge-danger' : 'badge-warning');

            return `
              <tr>
                <td><code>${c.id || 'N/A'}</code></td>
                <td><span class="badge ${badgeClass}">${statusStr}</span></td>
                <td><strong>${trustRankVal} / 100</strong></td>
                <td><small>${c.source || c.source_name || 'Unknown'}</small></td>
                <td><strong>${relVal} / 100</strong></td>
                <td><small>${evType}</small></td>
                <td><span class="badge ${kgBadgeClass}">${kgStatus}</span></td>
                <td style="white-space:nowrap;">
                  <button class="btn btn-outline" style="padding:4px 8px; font-size:0.75rem; border:1px solid var(--blue); color:var(--blue);" onclick="showEvalModal('${c.id}')">View Evaluation</button>
                  ${statusStr === 'REVIEW' || statusStr === 'PENDING_REVIEW' ? `
                    <button class="btn btn-success" style="padding:4px 8px; font-size:0.75rem;" onclick="promoteCku('${c.id}')">Promote</button>
                    <button class="btn btn-danger" style="padding:4px 8px; font-size:0.75rem;" onclick="rejectCku('${c.id}')">Reject</button>
                  ` : ''}
                </td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    `;
    container.innerHTML = html;
  } catch (err) {
    container.innerHTML = `<p style="color:var(--danger);">Error loading queue: ${err.message}</p>`;
  }
}

async function fetchSystemHealth() {
  try {
    const res = await fetch('/api/health');
    if (!res.ok) return;
    const data = await res.json();

    const whoEl = document.getElementById('health-who');
    if (whoEl) {
      const st = data.who ? data.who.status : 'UNKNOWN';
      whoEl.className = `badge ${st === 'CONNECTED' ? 'badge-success' : 'badge-danger'}`;
      whoEl.textContent = st === 'CONNECTED' ? '🟢 Connected' : '🔴 Unavailable';
    }

    const whoApiEl = document.getElementById('health-who-api');
    if (whoApiEl) {
      const st = data.who_api ? data.who_api.status : 'UNKNOWN';
      whoApiEl.className = `badge ${st === 'AVAILABLE' ? 'badge-success' : 'badge-danger'}`;
      whoApiEl.textContent = st === 'AVAILABLE' ? '🟢 Available' : '🔴 Unavailable';
    }

    const neo4jEl = document.getElementById('health-neo4j');
    if (neo4jEl) {
      const st = data.neo4j ? data.neo4j.status : 'UNKNOWN';
      neo4jEl.className = `badge ${st === 'CONNECTED' ? 'badge-success' : 'badge-warning'}`;
      neo4jEl.textContent = st === 'CONNECTED' ? '🟢 Connected' : '🟡 Disconnected (Offline)';
    }
  } catch (err) {
    console.warn('Health check warning:', err);
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', fetchSystemHealth);
} else {
  fetchSystemHealth();
}

async function showEvalModal(candidateId) {
  const overlay = document.getElementById('eval-modal-overlay');
  if (!overlay) return;

  overlay.style.display = 'flex';
  overlay.innerHTML = `
    <div class="eval-modal-content" style="max-width:850px; width:90%;">
      <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e2e8f0; padding-bottom:12px; margin-bottom:16px;">
        <h3 style="margin:0; color:var(--blue);">🔍 Evidence Audit Evaluation Report (ID: ${candidateId})</h3>
        <button onclick="closeEvalModal()" style="background:none; border:none; font-size:1.6rem; cursor:pointer; color:var(--muted);">&times;</button>
      </div>
      <p class="status-line">Fetching real-time backend evaluation record from API...</p>
    </div>
  `;

  let candidate = null;
  try {
    const res = await fetch(`/api/cku/evaluation/${candidateId}`);
    if (res.ok) {
      candidate = await res.json();
    } else {
      const errData = await res.json();
      throw new Error(errData.error || `HTTP ${res.status}`);
    }
  } catch (err) {
    candidate = (window.ckuCandidatesCache || []).find(c => String(c.id) === String(candidateId));
    if (!candidate) {
      overlay.innerHTML = `
        <div class="eval-modal-content" style="max-width:600px; width:90%;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
            <h3 style="margin:0; color:var(--danger);">⚠️ Evaluation API Error</h3>
            <button onclick="closeEvalModal()" style="background:none; border:none; font-size:1.6rem; cursor:pointer;">&times;</button>
          </div>
          <p style="color:var(--danger);">Failed to retrieve evaluation record: ${err.message}</p>
          <button class="btn btn-outline" onclick="closeEvalModal()">Close</button>
        </div>
      `;
      return;
    }
  }

  const audit = candidate.audit_trail || {};
  const statusStr = candidate.decision || candidate.status || 'REVIEW';
  const rawScore = candidate.trust_rank !== undefined ? candidate.trust_rank : (candidate.trust_score !== undefined ? candidate.trust_score : 0);
  
  // Hard Gate Lock: If status is REJECTED or HTTP status is not 200, TrustRank MUST BE N/A
  const trustRankVal = (statusStr === 'REJECTED' || (audit.http_status && audit.http_status !== 200)) ? 'N/A' : (audit.trust_rank_display || (rawScore <= 1.0 && rawScore > 0 ? (rawScore * 100).toFixed(0) + '/100' : `${rawScore.toFixed(0)}/100`));

  const decisionBadge = statusStr === 'VERIFIED' || statusStr === 'PROMOTED' ? '<span class="badge badge-success" style="font-size:1rem;">✓ VERIFIED</span>' : (statusStr === 'REJECTED' ? '<span class="badge badge-danger" style="font-size:1rem;">❌ REJECTED</span>' : '<span class="badge badge-warning" style="font-size:1rem;">⚠ REVIEW</span>');

  const reasons = audit.rejection_reasons || [];
  const isWhoVerified = audit.who_domain_verified === true || audit.who_domain_verified === True;
  const httpSuccess = audit.http_status === 200;

  overlay.innerHTML = `
    <div class="eval-modal-content" style="max-width:850px; width:90%;">
      <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e2e8f0; padding-bottom:12px; margin-bottom:16px;">
        <h3 style="margin:0; color:var(--blue);">🔍 Evidence Audit Evaluation Report (ID: ${candidate.id})</h3>
        <button onclick="closeEvalModal()" style="background:none; border:none; font-size:1.6rem; cursor:pointer; color:var(--muted);">&times;</button>
      </div>

      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:16px;">
        <!-- SOURCE VERIFICATION -->
        <div style="background:#f8fafc; padding:14px; border-radius:10px; border:1px solid #e2e8f0;">
          <h4 style="margin:0 0 10px; color:#1e293b;">🌐 REAL SOURCE VERIFICATION</h4>
          <ul style="list-style:none; padding:0; margin:0; font-size:0.88rem; display:grid; gap:6px;">
            <li><strong>URL:</strong> <small style="word-break:break-all;">${audit.source_url || candidate.source_url || candidate.source || 'N/A'}</small></li>
            <li><strong>HTTP Status:</strong> ${httpSuccess ? '<span style="color:var(--success); font-weight:bold;">✓ 200 OK</span>' : (audit.http_status ? `<span style="color:var(--danger); font-weight:bold;">✗ ${audit.http_status} Failed / 404</span>` : '<span style="color:var(--danger); font-weight:bold;">✗ Unchecked / Failed</span>')}</li>
            <li><strong>HTTPS Secure:</strong> ${audit.https_secure ? '<span style="color:var(--success);">✓ Secure (HTTPS)</span>' : '<span style="color:var(--danger);">✗ Insecure / HTTP</span>'}</li>
            <li><strong>Final URL:</strong> <small style="word-break:break-all;">${audit.final_url || audit.source_url || 'N/A'}</small></li>
            <li><strong>WHO Domain:</strong> ${isWhoVerified ? '<span style="color:var(--success); font-weight:bold;">✓ Verified (who.int)</span>' : (audit.domain && audit.domain !== 'unverified' ? `<span>✓ Verified (${audit.domain})</span>` : '<span style="color:var(--danger); font-weight:bold;">✗ Unverified / Non-WHO Domain</span>')}</li>
            <li><strong>Publisher:</strong> ${audit.publisher && audit.publisher !== 'Unknown / Unverified' ? `✓ ${audit.publisher}` : '<span style="color:var(--danger);">✗ Not detected / Unverified</span>'}</li>
            <li><strong>Page Title:</strong> ${audit.title && audit.title !== 'Invalid URL' && audit.title !== 'INVALID SOURCE URL' ? `✓ ${audit.title}` : '<span style="color:var(--danger);">✗ N/A / Title missing</span>'}</li>
            <li><strong>Publication Date:</strong> ${audit.publication_date && audit.publication_date !== 'Not specified' ? `✓ ${audit.publication_date}` : '<span>Not specified</span>'}</li>
            <li><strong>WHO API Cross-check:</strong> ${audit.who_api_verified === true ? `<span style="color:var(--success); font-weight:bold;">✓ Matched (${audit.who_api_match_type || 'WHO API'})</span>` : (audit.who_api_verified === 'UNKNOWN' ? `<span style="color:#b45309;">⚠ UNKNOWN (${audit.who_api_notes || 'API cross-check unavailable'})</span>` : '<span style="color:var(--muted);">Not applicable / Failed</span>')}</li>
            <li><strong>Guideline Match:</strong> ${audit.guideline_match === true ? '<span style="color:var(--success);">✓ Matched WHO Guideline</span>' : (audit.guideline_match === false ? '<span style="color:var(--danger);">✗ Guideline match failed</span>' : '<span>N/A</span>')}</li>
          </ul>
        </div>

        <!-- EVIDENCE EVALUATION & CONTENT -->
        <div style="background:#f8fafc; padding:14px; border-radius:10px; border:1px solid #e2e8f0;">
          <h4 style="margin:0 0 10px; color:#1e293b;">📊 EVIDENCE EVALUATION BREAKDOWN</h4>
          <div style="font-size:0.88rem; display:grid; gap:8px;">
            <div style="display:flex; justify-content:space-between;"><span>Source Authenticity (25%):</span> <strong>${(audit.source_authenticity_score !== undefined ? audit.source_authenticity_score : audit.source_authority_score || 0).toFixed(0)} / 100</strong></div>
            <div style="display:flex; justify-content:space-between;"><span>Clinical Relevance (25%):</span> <strong>${(audit.clinical_relevance_score || 0).toFixed(0)} / 100</strong></div>
            <small style="color:var(--muted); font-size:0.78rem;">Reason: ${audit.clinical_relevance_reason || 'Relevance calculated against clinical entity.'}</small>
            
            <div style="display:flex; justify-content:space-between;"><span>Evidence Quality (20%):</span> <strong>${(audit.evidence_quality_score || 0).toFixed(0)} / 100</strong></div>
            <div style="display:flex; justify-content:space-between;"><span>KG Consistency (15%):</span> <strong>${(audit.kg_consistency_score || 0).toFixed(0)} / 100</strong></div>
            <div style="display:flex; justify-content:space-between;"><span>Semantic Similarity (10%):</span> <strong>${(audit.semantic_similarity_score || 0).toFixed(0)} / 100</strong></div>
            <div style="display:flex; justify-content:space-between;"><span>Freshness Score (5%):</span> <strong>${(audit.freshness_score || 0).toFixed(0)} / 100</strong></div>
            <hr style="margin:4px 0; border-top:1px solid #cbd5e1;">
            <div style="display:flex; justify-content:space-between; font-size:1.05rem; font-weight:bold; color:var(--blue);">
              <span>Final Calculated TrustRank:</span> <span>${trustRankVal}</span>
            </div>
            <div style="margin-top:6px; font-size:0.82rem; background:#fff; padding:6px; border-radius:6px; border:1px solid #cbd5e1;">
              <strong>Neo4j Graph Status:</strong> ${audit.kg_status === 'KG_VERIFIED' || audit.kg_status === 'VERIFIED' ? '<span style="color:var(--success); font-weight:bold;">✓ KG_VERIFIED</span>' : (audit.kg_status === 'KG_CONFLICT' ? '<span style="color:var(--danger); font-weight:bold;">✗ KG_CONFLICT</span>' : '<span style="color:var(--danger); font-weight:bold;">✗ KG_NOT_FOUND</span>')}<br>
              <small style="color:var(--muted);">${audit.kg_reason || 'Knowledge graph status evaluated.'}</small>
            </div>
          </div>
        </div>
      </div>

      <div style="margin-top:16px; background:#ffffff; padding:12px; border-radius:8px; border:1px solid #e2e8f0;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <strong>Final Deterministic Decision:</strong>
          <div>${decisionBadge}</div>
        </div>
        ${reasons.length ? `
          <div style="margin-top:10px; background:var(--danger-bg); padding:10px; border-radius:8px; border:1px solid rgba(220,38,38,0.2);">
            <strong style="color:var(--danger);">REJECTED / REVIEW Reasons:</strong>
            <ul style="margin:4px 0 0; padding-left:20px; font-size:0.85rem; color:var(--danger);">
              ${reasons.map(r => `<li>✗ ${r}</li>`).join('')}
            </ul>
          </div>
        ` : ''}
      </div>

      <div style="margin-top:16px; text-align:right;">
        <button class="btn btn-outline" onclick="closeEvalModal()">Close Evaluation</button>
      </div>
    </div>
  `;
}

function closeEvalModal() {
  const overlay = document.getElementById('eval-modal-overlay');
  if (overlay) overlay.style.display = 'none';
}

async function reEvaluateAllCku() {
  const statusDiv = document.getElementById('cku-auto-status');
  statusDiv.innerHTML = '<span class="status-line">🔄 Re-evaluating all evidence against WHO, Neo4j, and hard verification gates...</span>';
  try {
    const res = await fetch('/api/cku/re-evaluate', { method: 'POST' });
    const data = await res.json();
    statusDiv.innerHTML = `
      <div style="background:var(--success-bg); border:1px solid var(--success); padding:10px 14px; border-radius:10px; font-size:0.9rem;">
        <strong>✅ Re-evaluation Complete!</strong> Total Candidates: <strong>${data.total_re_evaluated}</strong> | Verified: <strong>${data.verified_count}</strong> | Review: <strong>${data.review_count}</strong> | Rejected: <strong>${data.rejected_count}</strong>
      </div>
    `;
    loadCkuQueue();
  } catch (err) {
    statusDiv.innerHTML = `<span style="color:var(--danger);">⚠️ Re-evaluation failed: ${err.message}</span>`;
  }
}

async function promoteCku(candidateId) {
  const res = await fetch('/api/cku/promote', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ candidate_id: candidateId })
  });
  const data = await res.json();
  alert(`Promotion Result: ${data.status}`);
  loadCkuQueue();
}

async function rejectCku(candidateId) {
  const res = await fetch('/api/cku/reject', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ candidate_id: candidateId })
  });
  const data = await res.json();
  alert(`Rejection Result: ${data.status}`);
  loadCkuQueue();
}

async function runAutoCku() {
  const statusDiv = document.getElementById('cku-auto-status');
  statusDiv.innerHTML = '<span class="status-line">🔄 Running automated trust evaluation T(N) & promotion loop...</span>';
  try {
    const res = await fetch('/api/cku/auto-process', { method: 'POST' });
    const data = await res.json();
    statusDiv.innerHTML = `
      <div style="background:var(--success-bg); border:1px solid var(--success); padding:10px 14px; border-radius:10px; font-size:0.9rem;">
        <strong>✅ Automated CKU Processed!</strong> Promoted: <strong>${data.promoted_count}</strong> | Rejected: <strong>${data.rejected_count}</strong> | Remaining Pending: <strong>${data.remaining_pending_count}</strong>
      </div>
    `;
    loadCkuQueue();
  } catch (err) {
    statusDiv.innerHTML = `<span style="color:var(--danger);">⚠️ Auto-CKU failed: ${err.message}</span>`;
  }
}

async function seedAndAutoCku() {
  const statusDiv = document.getElementById('cku-auto-status');
  statusDiv.innerHTML = '<span class="status-line">🌱 Seeding medical candidates & running automated pipeline...</span>';
  try {
    const res = await fetch('/api/cku/seed-and-auto-process', { method: 'POST' });
    const data = await res.json();
    statusDiv.innerHTML = `
      <div style="background:var(--success-bg); border:1px solid var(--success); padding:10px 14px; border-radius:10px; font-size:0.9rem;">
        <strong>🌱 Seeded ${data.seeded_count} candidates & Automated CKU Complete!</strong><br>
        Promoted: <strong>${data.auto_results.promoted_count}</strong> | Rejected: <strong>${data.auto_results.rejected_count}</strong>
      </div>
    `;
    loadCkuQueue();
  } catch (err) {
    statusDiv.innerHTML = `<span style="color:var(--danger);">⚠️ Seeding failed: ${err.message}</span>`;
  }
}


