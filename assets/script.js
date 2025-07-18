const style = document.createElement('style');
style.textContent = '.message-field {margin-bottom: 0; min-height: 108px; height: calc(100% - 66px); border-radius: 2px 2px 0 0;} .markup-field {user-select: none; margin-bottom: 2px; padding: 0 4px; height: 18px; background: var(--inv-text); border: 1px solid var(--border); border-top: none; border-radius: 0 0 2px 2px;} .markup-button {cursor: pointer; margin-right: 4px;} .markup-button:hover {color: var(--btn-hover);} .markup-button[data-markup="quote"] {color: var(--quote);} .markup-button[data-markup="spoiler"] {background: var(--spoiler);} .markup-button[data-markup="strike"] {text-decoration: line-through;} .markup-button[data-markup="italic"] {font-style: italic;} .char-counter {float: right; color: var(--secondary);} .char-counter.low {color: var(--link-hover);} .file-viewer {position: fixed; top: 0; left: 0; width: 100%; height: 100%; display: flex; justify-content: center; align-items: center; z-index: 3;} .file-container {max-width: 90%; max-height: 90%; position: relative;} .file-container img, .file-container video {max-width: 100%; max-height: 90vh; object-fit: contain; background: var(--btn-background); border: 1px solid var(--text); user-select: none; transform-origin: center;} .video-wrapper {position: relative; display: inline-block;} .drag-handle {position: absolute; top: 0; left: 0; right: 0; height: calc(100% - 45px);} .post-preview {position: absolute; z-index: 2; padding: 0 2px; background: var(--obj-background); border: 1px solid var(--text); border-radius: 2px;} .file-upload {position: relative; overflow: hidden; cursor: pointer; height: 22px; width: calc(100% - 140px); padding: 0 4px; border: 1px solid var(--border); border-radius: 2px;} .file-upload-text {pointer-events: none; margin: 2px 0;} .file-previews {display: flex; gap: 4px; align-items: center; height: 100%;} .file-preview {position: relative; height: 20px; width: 20px; flex-shrink: 0;} .file-preview img {width: 100%; height: 100%; object-fit: cover;} .file-preview-empty {width: 100%; height: 100%; border: 1px dashed var(--text);} .file-preview-remove {display: none; position: absolute; top: 0; right: 0; width: 100%; height: 100%; font-size: initial; font-weight: bold; text-align: center; cursor: pointer; user-select: none; background: rgba(0,0,0,0.2); color: var(--link-hover);} .file-preview:hover .file-preview-remove {display: block;}';
document.head.appendChild(style);

const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
const messageField = document.querySelector('.message-field');
const markupField = document.createElement('div');
markupField.className = 'markup-field';
messageField.parentNode.insertBefore(markupField, messageField.nextSibling);

const markupButtons = ['>', '[sp]', '[s]', '[i]'].map((text, index) => {
  const button = document.createElement('span');
  button.className = 'markup-button';
  button.textContent = text;
  button.dataset.markup = ['quote', 'spoiler', 'strike', 'italic'][index];
  return markupField.appendChild(button);
});

const markupReplacements = {
  quote: text => `>${text.split('\n').join('\n>')}`,
  spoiler: text => `[sp]${text}[/sp]`,
  strike: text => `[s]${text}[/s]`,
  italic: text => `[i]${text}[/i]`
};

const cursorOffsets = {quote: 1, spoiler: 4, strike: 3, italic: 3};

const handleMarkupClick = event => {
  if (!event.target.classList.contains('markup-button')) return;
  const markup = event.target.dataset.markup;
  const start = messageField.selectionStart;
  const end = messageField.selectionEnd;
  const selectedText = messageField.value.substring(start, end);
  const replacement = markupReplacements[markup](selectedText);
  messageField.value = messageField.value.substring(0, start) + replacement + messageField.value.substring(end);
  messageField.focus();
  const newPosition = start + cursorOffsets[markup] + selectedText.length;
  messageField.setSelectionRange(newPosition, newPosition);
  updateCharCounter();
};

markupField.addEventListener('click', handleMarkupClick);

const charCounter = document.createElement('span');
charCounter.className = 'char-counter';
markupField.appendChild(charCounter);

const maxMessageLength = messageField.maxLength;
const updateCharCounter = () => {
  const remainingChars = maxMessageLength - messageField.value.length;
  charCounter.textContent = remainingChars;
  charCounter.classList.toggle('low', remainingChars <= 50);
};

messageField.addEventListener('input', updateCharCounter);
updateCharCounter();

const fileField = document.querySelector('.file-field');
if (fileField) {
  const fileUpload = document.createElement('div');
  fileUpload.className = 'file-upload';
  const fileInput = Object.assign(document.createElement('input'), {type: 'file', name: 'files[]', multiple: true, style: 'display: none'});
  const uploadText = Object.assign(document.createElement('div'), {className: 'file-upload-text', textContent: 'Прикрепить файлы'});
  const previewsContainer = document.createElement('div');
  previewsContainer.className = 'file-previews';
  fileUpload.append(fileInput, uploadText, previewsContainer);
  fileField.parentNode.insertBefore(fileUpload, fileField.nextSibling);
  fileField.remove();
  let currentFiles = [];
  const updatePreviews = files => {
    previewsContainer.innerHTML = '';
    uploadText.style.display = files.length ? 'none' : 'block';
    Array.from(files).forEach(file => {
      const preview = document.createElement('div');
      preview.className = 'file-preview';
      preview.title = file.name;
      const removeButton = Object.assign(document.createElement('div'), {
        className: 'file-preview-remove',
        textContent: '×',
        onclick: event => {
          event.stopPropagation();
          currentFiles = currentFiles.filter(f => f !== file);
          const newFiles = new DataTransfer();
          currentFiles.forEach(f => newFiles.items.add(f));
          fileInput.files = newFiles.files;
          updatePreviews(fileInput.files);
        }
      });
      if (file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.onload = event => preview.appendChild(Object.assign(document.createElement('img'), {src: event.target.result}));
        reader.readAsDataURL(file);
      } else {
        preview.appendChild(Object.assign(document.createElement('div'), {className: 'file-preview-empty'}));
      }
      preview.appendChild(removeButton);
      previewsContainer.appendChild(preview);
    });
  };
  const handleFiles = files => {
    const newFiles = new DataTransfer();
    currentFiles.push(...Array.from(files));
    currentFiles = currentFiles.slice(0, 4);
    currentFiles.forEach(file => newFiles.items.add(file));
    fileInput.files = newFiles.files;
    updatePreviews(fileInput.files);
  };
  fileUpload.onclick = () => fileInput.click();
  fileUpload.addEventListener('dragover', event => event.preventDefault());
  fileUpload.addEventListener('drop', event => {
    event.preventDefault();
    handleFiles(event.dataTransfer.files);
  });
  fileInput.onchange = event => {
    if (event.target.files.length) handleFiles(event.target.files);
  };
}

const handlePostClick = event => {
  const button = event.target.closest('.post-header a[href$="#postform"]');
  if (button) {
    const postId = button.closest('.post-header').querySelector('.post-number').textContent.slice(1);
    setTimeout(() => {
      messageField.value += `>>${postId}\n`;
      messageField.focus();
      messageField.setSelectionRange(messageField.value.length, messageField.value.length);
      updateCharCounter();
    }, 10);
    document.getElementById(postId)?.scrollIntoView({block: 'start'});
  }
};

document.body.addEventListener('click', handlePostClick);

const createFileContent = filePath => {
  const extension = filePath.split('.').pop().toLowerCase();
  if (['jpg', 'png', 'gif'].includes(extension)) return Object.assign(document.createElement('img'), {src: filePath, draggable: false});
  if (['mp4', 'webm'].includes(extension)) {
    const wrapper = document.createElement('div');
    wrapper.className = 'video-wrapper';
    const video = Object.assign(document.createElement('video'), {src: filePath, controls: true, draggable: false});
    const dragHandle = Object.assign(document.createElement('div'), {className: 'drag-handle'});
    wrapper.append(video, dragHandle);
    return wrapper;
  }
};

const setupDragAndZoom = (container, content) => {
  let scale = 1, isDragging = false, currentX = 0, currentY = 0, initialX = 0, initialY = 0, xOffset = 0, yOffset = 0;
  const handleMouseDown = event => {
    if (event.target === container || event.target === content || event.target.className === 'drag-handle') {
      event.preventDefault();
      initialX = event.clientX - xOffset;
      initialY = event.clientY - yOffset;
      isDragging = true;
    }
  };
  const handleMouseMove = event => {
    if (!isDragging) return;
    event.preventDefault();
    currentX = event.clientX - initialX;
    currentY = event.clientY - initialY;
    xOffset = currentX;
    yOffset = currentY;
    container.style.transform = `translate3d(${currentX}px, ${currentY}px, 0)`;
  };
  container.addEventListener('mousedown', handleMouseDown);
  document.addEventListener('mousemove', handleMouseMove);
  document.addEventListener('mouseup', () => isDragging = false);
  container.addEventListener('wheel', event => {
    if (!content.contains(event.target)) return;
    event.preventDefault();
    scale = Math.max(0.1, Math.min(scale + (event.deltaY > 0 ? -0.1 : 0.1), 5));
    content.style.transform = `scale(${scale})`;
  });
};

const openFileViewer = fileThumb => {
  const viewer = Object.assign(document.createElement('div'), {className: 'file-viewer'});
  const container = Object.assign(document.createElement('div'), {className: 'file-container'});
  const content = createFileContent(fileThumb.closest('a').href);
  container.appendChild(content);
  viewer.appendChild(container);
  document.body.appendChild(viewer);
  setupDragAndZoom(container, content);
  const closeViewer = () => {
    document.removeEventListener('keydown', handleKeyPress);
    viewer.remove();
  };
  const handleKeyPress = event => {
    if (event.key === 'Escape') return closeViewer();
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    const thumbs = Array.from(document.querySelectorAll('.file-thumb'));
    const currentIndex = thumbs.indexOf(fileThumb);
    const nextIndex = (currentIndex + (event.key === 'ArrowLeft' ? -1 : 1) + thumbs.length) % thumbs.length;
    closeViewer();
    openFileViewer(thumbs[nextIndex]);
  };
  document.addEventListener('keydown', handleKeyPress);
  viewer.addEventListener('click', event => {
    if (event.target === viewer || !content.contains(event.target)) closeViewer();
  });
};

if (!isTouchDevice) {
  document.body.addEventListener('click', event => {
    const fileLink = event.target.closest('a[href^="/media/"]');
    if (fileLink?.querySelector('.file-thumb') && !fileLink.hasAttribute('download')) {
      event.preventDefault();
      openFileViewer(fileLink.querySelector('.file-thumb'));
    }
  });
}
