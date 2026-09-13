// Native playback controls; chapter shortcuts stay inside the reading page.
document.querySelectorAll('.chapter-video').forEach(section => {
  const video = section.querySelector('video');
  const status = section.querySelector('.chapter-video-error');
  section.querySelectorAll('[data-video-time]').forEach(button => {
    button.addEventListener('click', async () => {
      const time = Number(button.dataset.videoTime);
      if (!Number.isFinite(time) || time < 0) return;
      status.hidden = true;
      try {
        video.currentTime = time;
        await video.play();
      } catch {
        status.textContent = 'Нажмите кнопку воспроизведения в проигрывателе. Если видео не открывается, его можно скачать по ссылке ниже.';
        status.hidden = false;
      }
    });
  });
  video.addEventListener('error', () => {
    status.textContent = 'Не удалось воспроизвести видео. Попробуйте открыть его снова или скачать файл по ссылке ниже.';
    status.hidden = false;
  });
});
