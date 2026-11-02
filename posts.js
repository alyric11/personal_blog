// Previews are optional; publishing and validation also work without JavaScript.
const editor = document.querySelector('#post-editor');
const picker = document.querySelector('#images');
const preview = document.querySelector('#image-preview');
const error = document.querySelector('#image-error');
let previewUrls = [];

function validateImages() {
    const kept = editor.querySelectorAll('input[name="remove"]:not(:checked)').length;
    const files = [...picker.files];
    let message = '';
    if (kept + files.length > 4) message = 'Choose up to four images in total.';
    else if (files.some(file => file.size > 5 * 1024 * 1024)) message = 'Each image must be 5 MB or smaller.';
    picker.setCustomValidity(message);
    error.textContent = message;
    error.hidden = !message;
}

function refreshPreviews() {
    previewUrls.forEach(url => URL.revokeObjectURL(url));
    previewUrls = [];
    preview.replaceChildren();
    validateImages();
    if (!picker.validity.valid) return;
    [...picker.files].forEach((file, index) => {
        const url = URL.createObjectURL(file);
        previewUrls.push(url);
        const image = document.createElement('img');
        image.src = url;
        image.alt = `New image ${index + 1}`;
        preview.append(image);
    });
}

picker.addEventListener('change', refreshPreviews);

editor.querySelectorAll('input[name="remove"]').forEach(box => {
    box.addEventListener('change', refreshPreviews);
});
