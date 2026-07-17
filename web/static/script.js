document.addEventListener('DOMContentLoaded', () => {
    let currentStage = 1;
    let uploadedFiles = { A: null, B: null };
    let clonesGenerated = false;
    let podcastGenerated = false;
    let currentDialog = null;

    const stage1 = document.getElementById('stage-1');
    const stage2 = document.getElementById('stage-2');
    const stage3 = document.getElementById('stage-3');
    const progressSteps = document.querySelectorAll('.progress-bar .step');

    function updateProgress(step) {
        progressSteps.forEach((el, index) => {
            el.classList.remove('active', 'completed');
            if (index + 1 < step) {
                el.classList.add('completed');
            } else if (index + 1 === step) {
                el.classList.add('active');
            }
        });
    }

    function showStage(stageNum) {
        currentStage = stageNum;
        stage1.classList.add('hidden');
        stage2.classList.add('hidden');
        stage3.classList.add('hidden');
        
        if (stageNum === 1) stage1.classList.remove('hidden');
        if (stageNum === 2) stage2.classList.remove('hidden');
        if (stageNum === 3) stage3.classList.remove('hidden');
        
        updateProgress(stageNum);
    }

    function formatDialogAsCards(dialog) {
        let html = '';
        
        if (dialog.title) {
            html += `<div class="dialog-header">${dialog.title}</div>`;
        }
        if (dialog.topic) {
            html += `<div class="dialog-topic">${dialog.topic}</div>`;
        }
        
        const entries = dialog.script || [];
        entries.forEach((entry, index) => {
            const speakerClass = entry.speaker === 'Host_B' ? 'speaker-b' : 'speaker-a';
            const speakerLabel = entry.speaker === 'Host_B' ? 'Speaker B' : 'Speaker A';
            html += `
                <div class="dialog-entry ${speakerClass}">
                    <div class="speaker-label">${speakerLabel}</div>
                    <div class="dialog-text">${entry.text}</div>
                </div>
            `;
        });
        
        return html;
    }

    async function handleFetchArticle() {
        const urlInput = document.getElementById('article-url');
        const fetchBtn = document.getElementById('fetch-btn');
        const loading = document.getElementById('stage-1-loading');
        const preview = document.getElementById('script-preview');
        const scriptContent = document.getElementById('script-content');

        const url = urlInput.value.trim();
        if (!url) {
            alert('Please enter a valid URL');
            return;
        }

        fetchBtn.disabled = true;
        loading.classList.remove('hidden');
        preview.classList.add('hidden');

        try {
            const response = await fetch('/api/fetch-article', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
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

    function setupDropZone(dropZone) {
        const speaker = dropZone.dataset.speaker;
        const fileInput = dropZone.querySelector('input[type="file"]');
        const content = dropZone.querySelector('.drop-zone-content');
        const fileInfo = dropZone.querySelector('.file-info');
        const filename = dropZone.querySelector('.filename');
        const audioPreview = dropZone.closest('.speaker-card').querySelector('.audio-preview');
        const audio = audioPreview.querySelector('audio');
        const removeBtn = dropZone.querySelector('.remove-btn');

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });

        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            const file = e.dataTransfer.files[0];
            if (file) handleFile(file);
        });

        fileInput.addEventListener('change', () => {
            if (fileInput.files[0]) {
                handleFile(fileInput.files[0]);
            }
        });

        removeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            resetDropZone();
        });

        function handleFile(file) {
            if (!file.name.endsWith('.wav')) {
                alert('Only WAV files are supported');
                return;
            }

            uploadedFiles[speaker] = file;
            filename.textContent = file.name;
            content.classList.add('hidden');
            fileInfo.classList.remove('hidden');
            audioPreview.classList.remove('hidden');
            
            const url = URL.createObjectURL(file);
            audio.src = url;

            checkGenerateClonesButton();
        }

        function resetDropZone() {
            uploadedFiles[speaker] = null;
            fileInput.value = '';
            content.classList.remove('hidden');
            fileInfo.classList.add('hidden');
            audioPreview.classList.add('hidden');
            audio.src = '';
            checkGenerateClonesButton();
        }
    }

    function checkGenerateClonesButton() {
        const btn = document.getElementById('generate-clones-btn');
        btn.disabled = !(uploadedFiles.A && uploadedFiles.B);
    }

    function checkProceedToStage3Button() {
        const btn = document.getElementById('proceed-stage-3');
        btn.disabled = !clonesGenerated;
    }

    async function uploadFile(speaker, file, transcript) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('speaker', speaker);
        formData.append('transcript', transcript);

        const response = await fetch('/api/upload-reference', {
            method: 'POST',
            body: formData
        });

        return response.json();
    }

    async function handleGenerateClones() {
        const btn = document.getElementById('generate-clones-btn');
        const status = document.getElementById('clone-status');
        const stepsList = document.getElementById('clone-steps');
        const complete = document.getElementById('clone-complete');

        btn.disabled = true;
        status.classList.remove('hidden');
        complete.classList.add('hidden');
        stepsList.innerHTML = '';

        try {
            const transcriptA = document.getElementById('transcript-a').value;
            const transcriptB = document.getElementById('transcript-b').value;

            await uploadFile('A', uploadedFiles.A, transcriptA);
            await uploadFile('B', uploadedFiles.B, transcriptB);

            const response = await fetch('/api/generate-clones', {
                method: 'POST'
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = JSON.parse(line.slice(6));
                        const li = document.createElement('li');
                        li.textContent = data.step;
                        li.classList.add('current');
                        
                        const prevCurrent = stepsList.querySelector('.current');
                        if (prevCurrent) {
                            prevCurrent.classList.remove('current');
                            prevCurrent.classList.add('done');
                        }
                        
                        stepsList.appendChild(li);
                    }
                }
            }

            const lastLi = stepsList.querySelector('.current');
            if (lastLi) {
                lastLi.classList.remove('current');
                lastLi.classList.add('done');
            }

            complete.classList.remove('hidden');
            clonesGenerated = true;
            checkProceedToStage3Button();
        } catch (err) {
            alert('Error generating voice clones: ' + err.message);
            btn.disabled = false;
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
            const response = await fetch('/api/generate-podcast', {
                method: 'POST'
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = JSON.parse(line.slice(6));
                        const li = document.createElement('li');
                        li.textContent = data.step;

                        if (data.status === 'done') {
                            li.classList.add('done');
                            stepsList.appendChild(li);

                            if (data.audio_url) {
                                const audio = document.getElementById('final-audio');
                                audio.querySelector('source').src = data.audio_url;
                                audio.load();
                            }
                            complete.classList.remove('hidden');
                            podcastGenerated = true;
                            return;
                        }

                        if (data.status === 'failed') {
                            li.classList.add('done');
                            li.style.color = 'var(--error)';
                            stepsList.appendChild(li);
                            btn.disabled = false;
                            return;
                        }

                        li.classList.add('current');
                        const prevCurrent = stepsList.querySelector('.current');
                        if (prevCurrent) {
                            prevCurrent.classList.remove('current');
                            prevCurrent.classList.add('done');
                        }
                        stepsList.appendChild(li);
                    }
                }
            }
        } catch (err) {
            alert('Error generating podcast: ' + err.message);
            btn.disabled = false;
        }
    }

    function resetToStage1() {
        clonesGenerated = false;
        podcastGenerated = false;
        currentDialog = null;
    }

    async function handleRestart() {
        try {
            await fetch('/api/reset', { method: 'POST' });
            resetToStage1();
            showStage(1);
            document.getElementById('article-url').value = '';
            document.getElementById('script-preview').classList.add('hidden');
            document.getElementById('clone-status').classList.add('hidden');
            document.getElementById('clone-complete').classList.add('hidden');
            document.getElementById('podcast-status').classList.add('hidden');
            document.getElementById('podcast-complete').classList.add('hidden');
            document.getElementById('transcript-a').value = '';
            document.getElementById('transcript-b').value = '';
            document.getElementById('voice-design-a').value = '';
            document.getElementById('voice-design-b').value = '';
            document.getElementById('voice-design-status').classList.add('hidden');
            document.getElementById('voice-design-steps').innerHTML = '';
            uploadedFiles = { A: null, B: null };
            
            const dropZones = document.querySelectorAll('.drop-zone');
            dropZones.forEach(zone => {
                zone.querySelector('.drop-zone-content').classList.remove('hidden');
                zone.querySelector('.file-info').classList.add('hidden');
                zone.closest('.speaker-card').querySelector('.audio-preview').classList.add('hidden');
            });
            
            checkGenerateClonesButton();
            checkProceedToStage3Button();
            checkDesignVoicesButton();
        } catch (err) {
            alert('Error: ' + err.message);
        }
    }

    document.getElementById('fetch-btn').addEventListener('click', handleFetchArticle);
    document.getElementById('back-to-url').addEventListener('click', () => showStage(1));
    document.getElementById('proceed-stage-2').addEventListener('click', () => showStage(2));
    document.getElementById('back-to-stage-1').addEventListener('click', () => showStage(1));
    document.getElementById('generate-clones-btn').addEventListener('click', handleGenerateClones);
    document.getElementById('proceed-stage-3').addEventListener('click', () => showStage(3));
    document.getElementById('back-to-stage-2').addEventListener('click', () => showStage(2));
    document.getElementById('generate-podcast-btn').addEventListener('click', handleGeneratePodcast);
    document.getElementById('restart-btn').addEventListener('click', handleRestart);

    document.querySelectorAll('.drop-zone').forEach(setupDropZone);

    const clonePanel = document.getElementById('voice-mode-clone');
    const designPanel = document.getElementById('voice-mode-design');
    const modeTabs = document.querySelectorAll('.voice-mode-tab');

    modeTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            modeTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            const mode = tab.dataset.mode;
            if (mode === 'clone') {
                clonePanel.classList.remove('hidden');
                designPanel.classList.add('hidden');
            } else {
                clonePanel.classList.add('hidden');
                designPanel.classList.remove('hidden');
            }
        });
    });

    document.querySelectorAll('.preset-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const speaker = chip.dataset.speaker;
            const desc = chip.dataset.desc;
            const textarea = document.getElementById(`voice-design-${speaker.toLowerCase()}`);
            textarea.value = desc;
            checkDesignVoicesButton();
        });
    });

    const designTextareas = document.querySelectorAll('.voice-design-textarea');
    designTextareas.forEach(ta => {
        ta.addEventListener('input', checkDesignVoicesButton);
    });

    function checkDesignVoicesButton() {
        const btn = document.getElementById('design-voices-btn');
        const descA = document.getElementById('voice-design-a').value.trim();
        const descB = document.getElementById('voice-design-b').value.trim();
        btn.disabled = !(descA && descB);
    }

    async function handleDesignVoices() {
        const btn = document.getElementById('design-voices-btn');
        const status = document.getElementById('voice-design-status');
        const stepsList = document.getElementById('voice-design-steps');
        const complete = document.getElementById('clone-complete');
        const statusClone = document.getElementById('clone-status');

        btn.disabled = true;
        status.classList.remove('hidden');
        stepsList.innerHTML = '';

        const descriptions = [
            { speaker: 'A', desc: document.getElementById('voice-design-a').value.trim(), language: 'English' },
            { speaker: 'B', desc: document.getElementById('voice-design-b').value.trim(), language: 'English' },
        ];

        try {
            for (const item of descriptions) {
                const li = document.createElement('li');
                li.textContent = `Designing voice for Speaker ${item.speaker}...`;
                li.classList.add('current');
                const prevCurrent = stepsList.querySelector('.current');
                if (prevCurrent) {
                    prevCurrent.classList.remove('current');
                    prevCurrent.classList.add('done');
                }
                stepsList.appendChild(li);

                const resp = await fetch('/api/voice-design', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(item),
                });

                const data = await resp.json();
                if (!data.success) {
                    li.textContent = `Speaker ${item.speaker}: ${data.error || 'Failed'}`;
                    li.classList.remove('current');
                    li.style.color = 'var(--error)';
                    btn.disabled = false;
                    return;
                }

                li.textContent = `Speaker ${item.speaker} voice designed.`;
                li.classList.remove('current');
                li.classList.add('done');
            }

            statusClone.classList.add('hidden');
            complete.classList.remove('hidden');
            clonesGenerated = true;
            checkProceedToStage3Button();
        } catch (err) {
            const li = document.createElement('li');
            li.textContent = 'Error: ' + err.message;
            li.style.color = 'var(--error)';
            stepsList.appendChild(li);
            btn.disabled = false;
        }
    }

    document.getElementById('design-voices-btn').addEventListener('click', handleDesignVoices);
});
