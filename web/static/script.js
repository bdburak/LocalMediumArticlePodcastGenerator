document.addEventListener('DOMContentLoaded', () => {
    let currentStage = 1;
    let currentDialog = null;
    let selectedVoices = { A: null, B: null };
    let allVoices = [];
    let creatingForSpeaker = null;
    let createUploadedFile = null;
    let createMode = 'clone';

    const stage1 = document.getElementById('stage-1');
    const stage2 = document.getElementById('stage-2');
    const stage3 = document.getElementById('stage-3');
    const progressSteps = document.querySelectorAll('.progress-bar .step');

    function updateProgress(step) {
        progressSteps.forEach((el, index) => {
            el.classList.remove('active', 'completed');
            if (index + 1 < step) el.classList.add('completed');
            else if (index + 1 === step) el.classList.add('active');
        });
    }

    function showStage(stageNum) {
        currentStage = stageNum;
        stage1.classList.add('hidden');
        stage2.classList.add('hidden');
        stage3.classList.add('hidden');
        if (stageNum === 1) stage1.classList.remove('hidden');
        if (stageNum === 2) { stage2.classList.remove('hidden'); loadVoiceLibrary(); }
        if (stageNum === 3) stage3.classList.remove('hidden');
        updateProgress(stageNum);
    }

    function checkProceedStage3() {
        document.getElementById('proceed-stage-3').disabled = !(selectedVoices.A && selectedVoices.B);
        const msg = document.getElementById('voice-selection-msg');
        if (selectedVoices.A && selectedVoices.B) msg.classList.remove('hidden');
        else msg.classList.add('hidden');
    }

    function renderVoiceCards() {
        ['A', 'B'].forEach(speaker => {
            const list = document.getElementById(`voice-${speaker.toLowerCase()}-list`);
            const selDiv = document.getElementById(`voice-${speaker.toLowerCase()}-selected`);
            list.innerHTML = '';

            if (allVoices.length === 0) {
                list.innerHTML = '<div class="empty-voices">No saved voices yet. Create one below.</div>';
                return;
            }

            allVoices.forEach(v => {
                const card = document.createElement('div');
                card.className = 'voice-card';
                card.dataset.name = v.name;

                const typeLabel = v.type === 'design' ? 'designed' : 'clone';
                const date = v.created_at ? new Date(v.created_at).toLocaleDateString() : '';

                card.innerHTML = `
                    <span class="voice-type-badge ${v.type}">${typeLabel}</span>
                    <div class="voice-card-info">
                        <div class="voice-card-name">${escapeHtml(v.name)}</div>
                        ${v.description ? `<div class="voice-card-desc">${escapeHtml(v.description)}</div>` : ''}
                        <div class="voice-card-date">${date}</div>
                    </div>
                    <button class="voice-delete-btn" title="Delete this voice">&times;</button>
                `;

                if (selectedVoices[speaker] === v.name) {
                    card.classList.add('selected');
                    selDiv.querySelector('.voice-name-display').textContent = v.name;
                    selDiv.querySelector('.voice-type-badge').textContent = typeLabel;
                    selDiv.querySelector('.voice-type-badge').className = 'voice-type-badge ' + v.type;
                    selDiv.classList.remove('hidden');
                }

                card.addEventListener('click', (e) => {
                    if (e.target.classList.contains('voice-delete-btn')) return;
                    selectVoice(speaker, v.name, v.type);
                });

                card.querySelector('.voice-delete-btn').addEventListener('click', (e) => {
                    e.stopPropagation();
                    deleteVoice(v.name);
                });

                list.appendChild(card);
            });
        });
    }

    async function selectVoice(speaker, name, type) {
        try {
            const resp = await fetch('/api/voices/select', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ display_name: name, speaker }),
            });
            const data = await resp.json();
            if (!data.success) { console.error(data.error); return; }

            selectedVoices[speaker] = name;
            renderVoiceCards();
            checkProceedStage3();
        } catch (err) { console.error(err); }
    }

    async function deleteVoice(name) {
        if (!confirm(`Delete voice "${name}"?`)) return;
        try {
            await fetch('/api/voices/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ display_name: name }),
            });
            if (selectedVoices.A === name) selectedVoices.A = null;
            if (selectedVoices.B === name) selectedVoices.B = null;
            allVoices = allVoices.filter(v => v.name !== name);
            renderVoiceCards();
            checkProceedStage3();
        } catch (err) { console.error(err); }
    }

    async function loadVoiceLibrary() {
        try {
            const resp = await fetch('/api/voices/library');
            allVoices = await resp.json();
            renderVoiceCards();
            checkProceedStage3();
        } catch (err) { console.error(err); }
    }

    function openCreatePanel(speaker) {
        creatingForSpeaker = speaker;
        document.getElementById('create-voice-title').textContent = `Create New Voice for Speaker ${speaker}`;
        document.getElementById('create-voice-panel').classList.remove('hidden');
        document.getElementById('create-voice-name').value = '';
        document.getElementById('create-voice-description').value = '';
        document.getElementById('create-transcript').value = '';
        document.getElementById('generate-create-btn').disabled = true;
        document.getElementById('create-voice-status').classList.add('hidden');
        resetCreateDropZone();
        setCreateMode('clone');
    }

    function closeCreatePanel() {
        document.getElementById('create-voice-panel').classList.add('hidden');
        creatingForSpeaker = null;
        createUploadedFile = null;
        resetCreateDropZone();
    }

    function setCreateMode(mode) {
        createMode = mode;
        document.querySelectorAll('#create-voice-panel .voice-mode-tab').forEach(t => {
            t.classList.toggle('active', t.dataset.mode === mode);
        });
        document.getElementById('vm-clone').classList.toggle('hidden', mode !== 'clone');
        document.getElementById('vm-design').classList.toggle('hidden', mode !== 'design');
        checkGenerateCreateBtn();
    }

    function checkGenerateCreateBtn() {
        const btn = document.getElementById('generate-create-btn');
        const name = document.getElementById('create-voice-name').value.trim();
        let ready = !!name;
        if (createMode === 'clone') ready = ready && !!createUploadedFile;
        else ready = ready && !!document.getElementById('create-voice-description').value.trim();
        btn.disabled = !ready;
    }

    function resetCreateDropZone() {
        createUploadedFile = null;
        const dz = document.getElementById('create-drop-zone');
        dz.querySelector('.drop-zone-content').classList.remove('hidden');
        dz.querySelector('.file-info').classList.add('hidden');
        dz.querySelector('input[type="file"]').value = '';
        dz.closest('.voice-mode-panel').querySelector('.audio-preview').classList.add('hidden');
    }

    function setupCreateDropZone() {
        const dz = document.getElementById('create-drop-zone');
        const fileInput = dz.querySelector('input[type="file"]');
        const content = dz.querySelector('.drop-zone-content');
        const fileInfo = dz.querySelector('.file-info');
        const filename = dz.querySelector('.filename');
        const audioPreview = dz.closest('.voice-mode-panel').querySelector('.audio-preview');
        const audio = audioPreview.querySelector('audio');
        const removeBtn = dz.querySelector('.remove-btn');

        dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('dragover'); });
        dz.addEventListener('dragleave', () => dz.classList.remove('dragover'));
        dz.addEventListener('drop', e => {
            e.preventDefault();
            dz.classList.remove('dragover');
            if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
        });
        fileInput.addEventListener('change', () => { if (fileInput.files[0]) handleFile(fileInput.files[0]); });
        removeBtn.addEventListener('click', e => { e.stopPropagation(); resetCreateDropZone(); checkGenerateCreateBtn(); });

        function handleFile(file) {
            if (!file.name.endsWith('.wav')) { alert('Only WAV files are supported'); return; }
            createUploadedFile = file;
            filename.textContent = file.name;
            content.classList.add('hidden');
            fileInfo.classList.remove('hidden');
            audioPreview.classList.remove('hidden');
            audio.src = URL.createObjectURL(file);
            checkGenerateCreateBtn();
        }
    }

    async function handleGenerateCreate() {
        const name = document.getElementById('create-voice-name').value.trim();
        const speaker = creatingForSpeaker;
        const btn = document.getElementById('generate-create-btn');
        const status = document.getElementById('create-voice-status');
        const steps = document.getElementById('create-voice-steps');

        btn.disabled = true;
        status.classList.remove('hidden');
        steps.innerHTML = '';

        function addStep(text, cls) {
            const li = document.createElement('li');
            li.textContent = text;
            if (cls) li.classList.add(cls);
            const prev = steps.querySelector('.current');
            if (prev) { prev.classList.remove('current'); prev.classList.add('done'); }
            steps.appendChild(li);
        }

        try {
            let voiceType = 'clone';

            if (createMode === 'clone') {
                addStep('Uploading and cloning voice...', 'current');
                const formData = new FormData();
                formData.append('file', createUploadedFile);
                formData.append('speaker', speaker);
                formData.append('transcript', document.getElementById('create-transcript').value);

                const resp = await fetch('/api/upload-reference', { method: 'POST', body: formData });
                const data = await resp.json();
                if (!data.success) throw new Error(data.error);
            } else {
                voiceType = 'design';
                addStep('Designing voice...', 'current');
                const desc = document.getElementById('create-voice-description').value.trim();
                const resp = await fetch('/api/voice-design', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ speaker, description: desc }),
                });
                const data = await resp.json();
                if (!data.success) throw new Error(data.error);
            }

            addStep('Saving voice...', 'current');
            const saveResp = await fetch('/api/voices/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    speaker,
                    display_name: name,
                    voice_type: voiceType,
                    description: createMode === 'design' ? document.getElementById('create-voice-description').value.trim() : '',
                }),
            });
            const saveData = await saveResp.json();
            if (!saveData.success) throw new Error(saveData.error);

            addStep('Done!', 'done');

            closeCreatePanel();
            selectedVoices[speaker] = name;
            await loadVoiceLibrary();
        } catch (err) {
            addStep('Error: ' + err.message, '');
            steps.lastChild.style.color = 'var(--error)';
            btn.disabled = false;
        }
    }

    function clearVoice(speaker) {
        selectedVoices[speaker] = null;
        document.getElementById(`voice-${speaker.toLowerCase()}-selected`).classList.add('hidden');
        renderVoiceCards();
        checkProceedStage3();
    }

    function formatDialogAsCards(dialog) {
        let html = '';
        if (dialog.title) html += `<div class="dialog-header">${dialog.title}</div>`;
        if (dialog.topic) html += `<div class="dialog-topic">${dialog.topic}</div>`;
        (dialog.script || []).forEach(entry => {
            const cls = entry.speaker === 'Host_B' ? 'speaker-b' : 'speaker-a';
            const label = entry.speaker === 'Host_B' ? 'Speaker B' : 'Speaker A';
            html += `<div class="dialog-entry ${cls}"><div class="speaker-label">${label}</div><div class="dialog-text">${entry.text}</div></div>`;
        });
        return html;
    }

    async function handleFetchArticle() {
        const urlInput = document.getElementById('article-url');
        const url = urlInput.value.trim();
        if (!url) { alert('Please enter a valid URL'); return; }

        const fetchBtn = document.getElementById('fetch-btn');
        const loading = document.getElementById('stage-1-loading');
        const preview = document.getElementById('script-preview');
        const scriptContent = document.getElementById('script-content');

        fetchBtn.disabled = true;
        loading.classList.remove('hidden');
        preview.classList.add('hidden');

        try {
            const response = await fetch('/api/fetch-article', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url }),
            });
            const data = await response.json();
            if (data.success) {
                currentDialog = data.dialog;
                scriptContent.innerHTML = formatDialogAsCards(currentDialog);
                preview.classList.remove('hidden');
            } else {
                alert(data.error || 'Failed to fetch article');
            }
        } catch (err) {
            alert('Error: ' + err.message);
        } finally {
            fetchBtn.disabled = false;
            loading.classList.add('hidden');
        }
    }

    async function handleGeneratePodcast() {
        const btn = document.getElementById('generate-podcast-btn');
        const status = document.getElementById('podcast-status');
        const stepsList = document.getElementById('podcast-steps');
        const complete = document.getElementById('podcast-complete');

        btn.disabled = true;
        status.classList.remove('hidden');
        complete.classList.add('hidden');
        stepsList.innerHTML = '';

        try {
            const response = await fetch('/api/generate-podcast', { method: 'POST' });
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const data = JSON.parse(line.slice(6));
                    const li = document.createElement('li');
                    li.textContent = data.step;

                    if (data.status === 'done') {
                        li.classList.add('done');
                        stepsList.appendChild(li);
                        if (data.audio_url) {
                            document.getElementById('final-audio').querySelector('source').src = data.audio_url;
                            document.getElementById('final-audio').load();
                        }
                        complete.classList.remove('hidden');
                        return;
                    }
                    if (data.status === 'failed') { li.classList.add('done'); li.style.color = 'var(--error)'; stepsList.appendChild(li); btn.disabled = false; return; }
                    li.classList.add('current');
                    const prev = stepsList.querySelector('.current');
                    if (prev) { prev.classList.remove('current'); prev.classList.add('done'); }
                    stepsList.appendChild(li);
                }
            }
        } catch (err) { alert('Error generating podcast: ' + err.message); btn.disabled = false; }
    }

    async function handleRestart() {
        try {
            await fetch('/api/reset', { method: 'POST' });
            selectedVoices = { A: null, B: null };
            currentDialog = null;
            showStage(1);
            document.getElementById('article-url').value = '';
            document.getElementById('script-preview').classList.add('hidden');
            document.getElementById('podcast-status').classList.add('hidden');
            document.getElementById('podcast-complete').classList.add('hidden');
            document.getElementById('voice-selection-msg').classList.add('hidden');
            closeCreatePanel();
            checkProceedStage3();
        } catch (err) { alert('Error: ' + err.message); }
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    document.getElementById('fetch-btn').addEventListener('click', handleFetchArticle);
    document.getElementById('back-to-url').addEventListener('click', () => showStage(1));
    document.getElementById('proceed-stage-2').addEventListener('click', () => showStage(2));
    document.getElementById('back-to-stage-1').addEventListener('click', () => showStage(1));
    document.getElementById('proceed-stage-3').addEventListener('click', () => showStage(3));
    document.getElementById('back-to-stage-2').addEventListener('click', () => showStage(2));
    document.getElementById('generate-podcast-btn').addEventListener('click', handleGeneratePodcast);
    document.getElementById('restart-btn').addEventListener('click', handleRestart);

    document.getElementById('create-voice-a-btn').addEventListener('click', () => openCreatePanel('A'));
    document.getElementById('create-voice-b-btn').addEventListener('click', () => openCreatePanel('B'));
    document.getElementById('cancel-create-btn').addEventListener('click', closeCreatePanel);
    document.getElementById('generate-create-btn').addEventListener('click', handleGenerateCreate);

    document.querySelectorAll('#create-voice-panel .voice-mode-tab').forEach(tab => {
        tab.addEventListener('click', () => setCreateMode(tab.dataset.mode));
    });

    document.querySelectorAll('#create-voice-panel .preset-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            document.getElementById('create-voice-description').value = chip.dataset.desc;
            checkGenerateCreateBtn();
        });
    });

    document.getElementById('create-voice-name').addEventListener('input', checkGenerateCreateBtn);
    document.getElementById('create-voice-description').addEventListener('input', checkGenerateCreateBtn);

    document.querySelectorAll('.clear-voice-btn').forEach(b => {
        b.addEventListener('click', () => clearVoice(b.closest('.voice-column').querySelector('.create-voice-btn').dataset.speaker));
    });

    setupCreateDropZone();
});
