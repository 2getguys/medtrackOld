document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('analysis_file');
    const fileNameSpan = document.getElementById('file-name');
    const uploadArea = document.querySelector('.upload-area'); // Добавлено для клика по области

    if (fileInput && fileNameSpan && uploadArea) {
        // Клик по области для выбора файла
        uploadArea.addEventListener('click', function() {
            fileInput.click(); // Симулируем клик по скрытому инпуту
        });

        // Обработчик изменения в input file
        fileInput.addEventListener('change', function() {
            if (fileInput.files.length > 0) {
                fileNameSpan.textContent = `Вибраний файл: ${fileInput.files[0].name}`;
            } else {
                fileNameSpan.textContent = 'Файл не вибрано';
            }
        });
    }
}); 