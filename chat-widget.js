(() => {
  let questionInput = document.querySelector('#question');
  const messages = document.querySelector('#messages');
  const sendButton = document.querySelector('#send');
  const microphoneButton = document.querySelector('#speak');
  const status = document.querySelector('#chat-status');
  if (!questionInput || !messages || !sendButton || !microphoneButton || !status) return;

  // Older translated pages still contain an input element. Upgrade it at runtime
  // so the larger, multiline composer works on those pages too.
  if (questionInput.tagName !== 'TEXTAREA') {
    const expandedInput = document.createElement('textarea');
    expandedInput.id = questionInput.id;
    expandedInput.className = questionInput.className;
    expandedInput.placeholder = questionInput.placeholder || 'Type your question here';
    expandedInput.value = questionInput.value;
    expandedInput.rows = 3;
    questionInput.replaceWith(expandedInput);
    questionInput = expandedInput;
  }

  const chatStyle = document.createElement('style');
  chatStyle.textContent = `
    #agent-drawer.assistant-drawer { width:min(680px,100vw)!important; padding:24px; }
    #agent-drawer .chatbox { min-height:0; width:100%; }
    #agent-drawer .messages { min-height:160px; flex:1; overflow:auto; }
    #agent-drawer .input-row { display:grid!important; grid-template-columns:auto auto minmax(130px,1fr) auto; gap:9px; align-items:stretch; }
    #agent-drawer #question { grid-column:1/-1; width:100%; min-width:0; min-height:126px; max-height:32vh; resize:vertical; overflow:auto; padding:14px; border:1px solid var(--line,#254233); border-radius:12px; background:#091710; color:var(--ink,#f2f5eb); font:inherit; font-size:16px; line-height:1.5; }
    #agent-drawer .input-row button { min-width:0; padding:10px 12px; white-space:normal; }
    #agent-drawer #speech-toggle[aria-pressed="true"] { border-color:var(--mint,#70dfae); color:var(--mint,#70dfae); }
    #agent-drawer #speech-toggle[aria-pressed="false"] { opacity:.82; }
    @media(max-width:560px) {
      #agent-drawer.assistant-drawer { width:100vw!important; padding:16px; }
      #agent-drawer .input-row { grid-template-columns:repeat(2,minmax(0,1fr)); }
      #agent-drawer #question { min-height:112px; }
    }
  `;
  document.head.append(chatStyle);

  const stopButton = document.createElement('button');
  stopButton.type = 'button';
  stopButton.id = 'stop-generation';
  stopButton.className = 'btn';
  stopButton.textContent = 'Stop response';
  stopButton.hidden = true;
  sendButton.insertAdjacentElement('afterend', stopButton);

  let speechEnabled = localStorage.getItem('nivesh-chat-speech') !== 'off';
  const speechToggle = document.createElement('button');
  speechToggle.type = 'button';
  speechToggle.id = 'speech-toggle';
  speechToggle.className = 'btn';
  speechToggle.setAttribute('aria-pressed', String(speechEnabled));
  sendButton.parentElement.append(speechToggle);
  speechToggle.insertAdjacentElement('afterend', microphoneButton);
  const speechNotice = document.createElement('div');
  speechNotice.className = 'small';
  speechNotice.id = 'chat-speech-note';
  status.insertAdjacentElement('afterend', speechNotice);
  const updateSpeechToggle = () => {
    speechToggle.setAttribute('aria-pressed', String(speechEnabled));
    speechToggle.textContent = speechEnabled ? '🔊 Speech on' : '🔇 Speech off';
    speechToggle.title = speechEnabled ? 'Turn online spoken answers off' : 'Turn spoken answers on';
    speechNotice.textContent = speechEnabled
      ? 'Speech follows the selected language. Online voices cover English, Bengali, Gujarati, Hindi, Kannada, Malayalam, Marathi, Nepali, Punjabi, Tamil, Telugu, and Urdu; other languages need a matching voice installed on this device. Internet access is required.'
      : 'Speech is off; replies remain available as text.';
  };
  updateSpeechToggle();

  // A failed request for one locale must not disable speech for all later
  // locales. Changing the website language also cancels queued old-language
  // audio so the next answer starts cleanly in the newly selected language.
  document.querySelector('#language')?.addEventListener('change', () => {
    clearSpeech();
    speechUnavailable = false;
    status.dataset.explicit = '';
    idleMessage = `Speech ready for ${languageName()}.`;
    updateControls();
  });

  // IndicConformer provides separate models for English and all 22 scheduled
  // Indian languages. The selected model is fetched on first use.
  const supportedSpeech = new Set([
    'en', 'as', 'bn', 'brx', 'doi', 'gu', 'hi', 'kn', 'ks', 'kok', 'mai',
    'ml', 'mni', 'mr', 'ne', 'or', 'pa', 'sa', 'sat', 'sd', 'ta', 'te', 'ur'
  ]);
  const supportedWebsiteLanguages = new Set([
    'en', 'as', 'bn', 'brx', 'doi', 'gu', 'hi', 'kn', 'ks', 'kok', 'mai',
    'ml', 'mni', 'mr', 'ne', 'or', 'pa', 'sa', 'sat', 'sd', 'ta', 'te', 'ur'
  ]);
  const translatedPageLanguage = () => {
    const filename = decodeURIComponent(location.pathname).split('/').pop() || '';
    const match = filename.match(/-([a-z]{2,3})\.html$/i);
    const code = match?.[1]?.toLowerCase();
    return code && supportedWebsiteLanguages.has(code) ? code : '';
  };
  const pageLanguage = translatedPageLanguage();
  const languageSelect = document.querySelector('#language');
  // A translated file's suffix is authoritative. Old cached language state
  // could leave the selector on English even while index-te.html is displayed.
  if (pageLanguage && languageSelect) {
    languageSelect.value = pageLanguage;
    const firstLanguage = document.querySelector('#first-language');
    if (firstLanguage) firstLanguage.value = pageLanguage;
    localStorage.setItem('nivesh-language', pageLanguage);
    document.cookie = `nivesh_lang=${encodeURIComponent(pageLanguage)}; Path=/; SameSite=Lax`;
  }
  const languageCode = () => pageLanguage || languageSelect?.value || 'en';
  const languageName = () => {
    const code = languageCode();
    return [...(languageSelect?.options || [])].find(option => option.value === code)?.textContent || code;
  };
  const sentenceBoundary = /(?<=[^\d])[.!?।॥]+\s*|\n+/g;
  let isGenerating = false;
  let pendingSpeech = 0;
  let speechQueue = [];
  let activeSpeechJob = null;
  let speechUnavailable = false;
  let currentRequestId = '';
  let speechBuffer = '';
  let speechLines = [];
  let speechAudioContext = null;
  let idleMessage = 'Ready for your next question.';
  let recorder = null;
  let recorderStream = null;
  let recordingChunks = [];

  function updateControls() {
    pendingSpeech = speechQueue.length + (activeSpeechJob ? 1 : 0);
    sendButton.disabled = isGenerating || Boolean(recorder);
    microphoneButton.disabled = isGenerating;
    stopButton.hidden = !isGenerating;
    if (isGenerating && !status.dataset.explicit) status.textContent = 'Generating a detailed answer…';
    else if (pendingSpeech > 0 && !status.dataset.explicit) status.textContent = 'Answer complete; playing the queued speech…';
    else if (!isGenerating && pendingSpeech === 0 && !recorder && !status.dataset.explicit) status.textContent = idleMessage;
  }

  function clearSpeech() {
    if (activeSpeechJob) {
      activeSpeechJob.controller.abort();
      if (activeSpeechJob.audio) {
        activeSpeechJob.audio.onended = null;
        activeSpeechJob.audio.onerror = null;
        activeSpeechJob.audio.pause();
        activeSpeechJob.audio.src = '';
      }
      if (activeSpeechJob.utterance && 'speechSynthesis' in window) window.speechSynthesis.cancel();
      if (activeSpeechJob.source) {
        try { activeSpeechJob.source.stop(); } catch (_) {}
      }
      if (activeSpeechJob.url) URL.revokeObjectURL(activeSpeechJob.url);
    }
    speechQueue = [];
    activeSpeechJob = null;
    pendingSpeech = 0;
    speechBuffer = '';
    speechLines = [];
    updateControls();
  }

  function unlockAudioOutput() {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return null;
    try {
      if (!speechAudioContext) speechAudioContext = new AudioContextClass();
      if (speechAudioContext.state === 'suspended') speechAudioContext.resume().catch(() => {});
      return speechAudioContext;
    } catch (_) {
      return null;
    }
  }

  function cleanSpeechText(value) {
    return String(value || '')
      .replace(/```[\s\S]*?```/g, ' ')
      .replace(/`[^`]*`/g, ' ')
      .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replace(/\[([^\]]+)\]\((?:[^()]|\([^)]*\))*\)/g, '$1')
      .replace(/https?:\/\/\S+/gi, ' ')
      .replace(/<[^>]*>/g, ' ')
      .replace(/^\s{0,3}#{1,6}\s*/gm, '')
      .replace(/^\s*>+\s?/gm, '')
      .replace(/^\s*[-*+•▪◦]\s+/gm, '')
      .replace(/^\s*(?:[-*_]\s*){3,}$/gm, ' ')
      .replace(/^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/gm, ' ')
      .replace(/[|*_`~#]/g, '')
      .replace(/\\([\\`*_{}\[\]()#+.!|>~-])/g, '$1')
      .replace(/[ \t]+/g, ' ')
      .replace(/\s*\n\s*/g, ' ')
      .trim();
  }

  function speakSentence(text) {
    const cleanText = cleanSpeechText(text);
    if (!speechEnabled || speechUnavailable || !cleanText) return;
    // Capture the selected language for each segment. Reading the selector
    // later can race with a language switch while audio is being requested.
    speechQueue.push({text: cleanText, code: languageCode(), name: languageName()});
    updateControls();
    playNextSpeech();
  }

  function tryMatchingDeviceVoice(text, code, job, finish, languageLabel = code) {
    if (!('speechSynthesis' in window) || !window.SpeechSynthesisUtterance) return false;
    const voices = window.speechSynthesis.getVoices();
    const voice = voices.find(item => item.lang.toLowerCase() === `${code}-in`)
      || voices.find(item => item.lang.toLowerCase().split('-')[0] === code.toLowerCase());
    // Never let the browser silently use its default English voice for an
    // unsupported language; only use a device voice that matches the selection.
    if (!voice) return false;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = voice.lang;
    utterance.voice = voice;
    job.utterance = utterance;
    utterance.onend = () => finish();
    utterance.onerror = () => finish(`This device could not speak ${languageLabel}. The text answer is still available.`);
    try {
      if (window.speechSynthesis.paused) window.speechSynthesis.resume();
      window.speechSynthesis.speak(utterance);
      return true;
    } catch (_) {
      return false;
    }
  }

  async function playNextSpeech() {
    if (!speechEnabled || activeSpeechJob || !speechQueue.length) return;
    const speech = speechQueue.shift();
    const {text, code, name} = speech;
    const job = {controller: new AbortController(), audio: null, source: null, url: ''};
    activeSpeechJob = job;
    updateControls();
    const finish = errorMessage => {
      if (activeSpeechJob !== job) return;
      activeSpeechJob = null;
      if (job.url) URL.revokeObjectURL(job.url);
      if (errorMessage) {
        speechUnavailable = true;
        speechQueue = [];
        status.textContent = errorMessage;
        status.dataset.explicit = 'true';
      }
      updateControls();
      if (!errorMessage) playNextSpeech();
    };
    try {
      let response;
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          response = await fetch('/api/chat/speech', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text, lang: code}),
            signal: job.controller.signal,
          });
          // A retry can recover from a brief network/service interruption;
          // unsupported locales (400) should go straight to a local voice.
          if (response.ok || response.status < 500 || attempt === 1) break;
        } catch (error) {
          if (error.name === 'AbortError' || attempt === 1) throw error;
        }
        await new Promise((resolve, reject) => {
          const timer = setTimeout(resolve, 350);
          job.controller.signal.addEventListener('abort', () => {
            clearTimeout(timer);
            reject(new DOMException('Speech request cancelled', 'AbortError'));
          }, {once: true});
        });
      }
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || data.detail || `Speech generation failed (HTTP ${response.status}).`);
      }
      job.url = URL.createObjectURL(await response.blob());
      if (activeSpeechJob !== job) {
        URL.revokeObjectURL(job.url);
        return;
      }
      const context = unlockAudioOutput();
      if (context) {
        try {
          if (context.state === 'suspended') await context.resume();
          const audioBuffer = await context.decodeAudioData(await (await fetch(job.url)).arrayBuffer());
          if (activeSpeechJob !== job) return;
          job.source = context.createBufferSource();
          job.source.buffer = audioBuffer;
          job.source.connect(context.destination);
          job.source.onended = () => finish();
          job.source.start(0);
          return;
        } catch (_) {
          if (activeSpeechJob !== job) return;
        }
      }
      job.audio = new Audio(job.url);
      job.audio.onended = () => finish();
      job.audio.onerror = () => {
        if (!tryMatchingDeviceVoice(text, code, job, finish, name)) {
          finish(`Audio playback failed for ${name}. The text answer is still available.`);
        }
      };
      await job.audio.play();
    } catch (error) {
      if (activeSpeechJob !== job || error.name === 'AbortError') return;
      if (tryMatchingDeviceVoice(text, code, job, finish, name)) return;
      finish(error.message || `Could not play the ${name} answer. The text answer is still available.`);
    }
  }

  speechToggle.onclick = () => {
    speechEnabled = !speechEnabled;
    if (speechEnabled) unlockAudioOutput();
    localStorage.setItem('nivesh-chat-speech', speechEnabled ? 'on' : 'off');
    updateSpeechToggle();
    speechUnavailable = false;
    if (!speechEnabled) clearSpeech();
    status.dataset.explicit = 'true';
    status.textContent = speechEnabled ? 'Spoken answers use the selected website language.' : 'Spoken answers are off.';
  };

  function speakReadySentences() {
    let match;
    while ((match = sentenceBoundary.exec(speechBuffer)) !== null) {
      const sentence = speechBuffer.slice(0, match.index + match[0].length).trim();
      speechBuffer = speechBuffer.slice(match.index + match[0].length);
      if (sentence) speechLines.push(sentence);
      if (speechLines.length >= 3) speakSentence(speechLines.splice(0, 3).join(' '));
      sentenceBoundary.lastIndex = 0;
    }
  }

  function flushSpeechTail() {
    const tail = [...speechLines, speechBuffer.trim()].filter(Boolean).join(' ');
    speechLines = [];
    speechBuffer = '';
    if (tail) speakSentence(tail);
  }

  function newRequestId() {
    return window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function appendEvent(event, answer, messageBox) {
    if (event.type === 'status') {
      status.textContent = event.text;
      return;
    }
    if (event.type === 'reset') {
      // Older servers may still send reset; never erase useful output or
      // trigger a second generation for that legacy event.
      status.textContent = 'Repeated phrasing detected. Keeping the answer generated so far.';
      status.dataset.explicit = 'true';
      return;
    }
    if (event.type === 'loop_stopped') {
      status.textContent = 'Repeated phrasing detected. Stopped the repetition and kept the answer generated so far.';
      status.dataset.explicit = 'true';
      return;
    }
    if (event.type === 'stopped') {
      clearSpeech();
      status.textContent = 'Response stopped.';
      status.dataset.explicit = 'true';
      return;
    }
    if (event.type === 'chunk') {
      answer.textContent += event.text || '';
      speechBuffer += event.text || '';
      speakReadySentences();
      messageBox.scrollTop = messageBox.scrollHeight;
      return;
    }
    if (event.type === 'error') throw new Error(event.error || 'The agent could not finish this answer.');
  }

  sendButton.onclick = async () => {
    const question = questionInput.value.trim();
    if (!question || isGenerating || recorder) return;
    if (speechEnabled) unlockAudioOutput();
    status.dataset.explicit = '';
    speechUnavailable = false;
    idleMessage = 'Ready for your next question.';
    const userMessage = document.createElement('div');
    userMessage.className = 'msg user';
    userMessage.textContent = question;
    messages.append(userMessage);
    questionInput.value = '';
    questionInput.style.height = '';
    const answer = document.createElement('div');
    answer.className = 'msg';
    answer.textContent = 'Connecting to the local learning agent…';
    messages.append(answer);
    messages.scrollTop = messages.scrollHeight;
    isGenerating = true;
    currentRequestId = newRequestId();
    speechBuffer = '';
    speechLines = [];
    updateControls();

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message: question, lang: languageCode(), request_id: currentRequestId})
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || `Agent server returned ${response.status}. Restart the website from the project folder and try again.`);
      }
      if (!response.body) throw new Error('This browser cannot receive streamed responses.');
      answer.textContent = '';
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let pending = '';
      while (true) {
        const {value, done} = await reader.read();
        pending += decoder.decode(value || new Uint8Array(), {stream: !done});
        let newline;
        while ((newline = pending.indexOf('\n')) >= 0) {
          const line = pending.slice(0, newline);
          pending = pending.slice(newline + 1);
          if (line.trim()) appendEvent(JSON.parse(line), answer, messages);
        }
        if (done) break;
      }
      if (pending.trim()) appendEvent(JSON.parse(pending), answer, messages);
      flushSpeechTail();
      if (!answer.textContent.trim()) answer.textContent = 'The agent returned an empty answer.';
    } catch (error) {
      if (error instanceof TypeError) answer.textContent = 'Cannot reach the local website server. Restart it with python setup_and_run.py and try again.';
      else answer.textContent = error.message || 'The answer did not complete.';
      clearSpeech();
      status.textContent = 'The answer did not complete. You can submit the question again.';
      status.dataset.explicit = 'true';
    } finally {
      isGenerating = false;
      currentRequestId = '';
      updateControls();
      messages.scrollTop = messages.scrollHeight;
    }
  };

  questionInput.onkeydown = event => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      sendButton.click();
    }
  };

  questionInput.addEventListener('input', () => {
    questionInput.style.height = 'auto';
    questionInput.style.height = `${Math.min(questionInput.scrollHeight, Math.round(window.innerHeight * 0.32))}px`;
  });

  stopButton.onclick = async () => {
    if (!isGenerating || !currentRequestId) return;
    stopButton.disabled = true;
    status.textContent = 'Stopping the response and speech…';
    status.dataset.explicit = 'true';
    clearSpeech();
    try {
      await fetch('/api/chat/stop', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({request_id: currentRequestId})
      });
    } catch (_) {
      // The generation request will also stop if the browser connection closes.
    } finally {
      stopButton.disabled = false;
    }
  };

  function makeMonoWav(audioBuffer, sampleRate = 16000) {
    const targetLength = Math.ceil(audioBuffer.length * sampleRate / audioBuffer.sampleRate);
    const channels = Array.from({length: audioBuffer.numberOfChannels}, (_, i) => audioBuffer.getChannelData(i));
    const samples = new Int16Array(targetLength);
    for (let i = 0; i < targetLength; i++) {
      const source = i * audioBuffer.sampleRate / sampleRate;
      const left = Math.floor(source);
      const fraction = source - left;
      let sample = 0;
      for (const channel of channels) {
        const first = channel[Math.min(left, channel.length - 1)] || 0;
        const second = channel[Math.min(left + 1, channel.length - 1)] || 0;
        sample += first + (second - first) * fraction;
      }
      sample /= channels.length || 1;
      samples[i] = Math.max(-32768, Math.min(32767, Math.round(sample < 0 ? sample * 32768 : sample * 32767)));
    }
    const buffer = new ArrayBuffer(44 + samples.byteLength);
    const view = new DataView(buffer);
    const tag = (offset, value) => [...value].forEach((char, i) => view.setUint8(offset + i, char.charCodeAt(0)));
    tag(0, 'RIFF'); view.setUint32(4, 36 + samples.byteLength, true); tag(8, 'WAVE'); tag(12, 'fmt ');
    view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true); view.setUint16(34, 16, true); tag(36, 'data');
    view.setUint32(40, samples.byteLength, true); new Int16Array(buffer, 44).set(samples);
    return new Blob([buffer], {type: 'audio/wav'});
  }

  async function transcribeRecording(blob) {
    const code = languageCode();
    if (!supportedSpeech.has(code)) {
      throw new Error('AI4Bharat voice input is available for English and all 22 supported Indian languages. Select the language spoken in the recording.');
    }
    status.textContent = `Converting the ${languageName()} recording to text…`;
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) throw new Error('This browser cannot decode the recording. Try a recent Chrome or Edge browser.');
    const context = new AudioContextClass();
    let decoded;
    try { decoded = await context.decodeAudioData(await blob.arrayBuffer()); }
    finally { await context.close().catch(() => {}); }
    const wav = makeMonoWav(decoded);
    if (wav.size > 25 * 1024 * 1024) throw new Error('This recording is too long. Keep it under about 10 minutes and try again.');
    let ready = false;
    for (let attempt = 0; attempt < 900; attempt++) {
      const health = await fetch('/api/fraud/status', {cache: 'no-store'});
      const state = await health.json().catch(() => ({}));
      if (!health.ok || state.state === 'error') {
        throw new Error(state.error || 'The website AI service is not ready. Restart the website and try again.');
      }
      if (state.state === 'ready') { ready = true; break; }
      status.textContent = `Loading the voice and audit models… (${attempt * 2}s)`;
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
    if (!ready) throw new Error('The voice model is still loading. Check fraud_backend.log and try again.');
    status.textContent = `Waiting for the local AI4Bharat ${languageName()} model…`;
    const form = new FormData();
    form.append('language', code);
    form.append('audio', wav, 'chat-voice-message.wav');
    status.textContent = `Sending audio to the ${languageName()} recognizer (${code})…`;
    const response = await fetch('/api/v1/transcribe-voice', {method: 'POST', body: form});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = data.detail || data.error;
      if (response.status === 400 && !detail) throw new Error('The running website is an older version that cannot receive audio uploads. Stop it and restart with python setup_and_run.py.');
      throw new Error(detail || `Transcription failed (HTTP ${response.status}).`);
    }
    const returnedLanguage = String(data.language || '').toLowerCase();
    if (returnedLanguage && returnedLanguage !== code) {
      const returnedName = data.language_name || returnedLanguage;
      throw new Error(`The speech server used ${returnedName} instead of ${languageName()}. No transcript was added. Restart the website with setup_and_run.py and try again.`);
    }
    if (!data.text?.trim()) throw new Error('No words were recognized. Check the spoken language and recording, then try again.');
    questionInput.value = questionInput.value.trim() ? `${questionInput.value.trim()}\n${data.text.trim()}` : data.text.trim();
    questionInput.focus();
    status.textContent = `Added the ${languageName()} transcript to the question. Review it, then press Ask.`;
    status.dataset.explicit = 'true';
  }

  microphoneButton.onclick = async () => {
    if (recorder) {
      if (recorder.state !== 'inactive') recorder.stop();
      return;
    }
    if (!supportedSpeech.has(languageCode())) {
      status.textContent = 'AI4Bharat voice input supports English and all 22 supported Indian languages. Select the website language spoken in the recording.';
      status.dataset.explicit = 'true';
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      status.textContent = 'This browser cannot record audio. Use a current Chrome or Edge browser.';
      status.dataset.explicit = 'true';
      return;
    }
    try {
      recorderStream = await navigator.mediaDevices.getUserMedia({audio: true});
      recordingChunks = [];
      recorder = new MediaRecorder(recorderStream);
      recorder.ondataavailable = event => { if (event.data?.size) recordingChunks.push(event.data); };
      recorder.onerror = () => {
        status.textContent = 'Could not record audio. Check microphone access and try again.';
        status.dataset.explicit = 'true';
      };
      recorder.onstop = async () => {
        const selectedRecorder = recorder;
        recorder = null;
        recorderStream?.getTracks().forEach(track => track.stop());
        recorderStream = null;
        microphoneButton.textContent = '🎙';
        microphoneButton.title = 'Record a voice question with AI4Bharat';
        updateControls();
        try {
          const blob = new Blob(recordingChunks, {type: selectedRecorder.mimeType || 'audio/webm'});
          recordingChunks = [];
          if (!blob.size) throw new Error('No audio was recorded. Speak clearly and try again.');
          await transcribeRecording(blob);
        } catch (error) {
          status.textContent = error.message || 'Voice transcription failed.';
          status.dataset.explicit = 'true';
        } finally {
          updateControls();
        }
      };
      status.dataset.explicit = 'true';
      status.textContent = `Recording in ${languageName()}. Select the microphone again when you finish.`;
      microphoneButton.textContent = '⏹';
      microphoneButton.title = 'Stop recording and transcribe';
      recorder.start();
      updateControls();
    } catch (error) {
      recorderStream?.getTracks().forEach(track => track.stop());
      recorderStream = null;
      status.textContent = error.name === 'NotAllowedError' ? 'Allow microphone access for this local website, then try again.' : (error.message || 'Could not start microphone recording.');
      status.dataset.explicit = 'true';
    }
  };

  status.dataset.explicit = '';
  updateControls();
})();
