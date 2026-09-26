const form = document.querySelector("[data-recipe-upload]");

if (form) {
  form.addEventListener("submit", (event) => {
    const file = form.elements.file.files[0];
    const status = form.querySelector("[data-upload-status]");
    if (!file) return;
    const limit = form.elements.kind.value === "video" ? 200 * 1024 * 1024 : 8 * 1024 * 1024;
    if (file.size > limit) {
      event.preventDefault();
      status.textContent = form.elements.kind.value === "video" ? "视频超过 200 MB，请选较小的文件。" : "图片超过 8 MB，请选较小的文件。";
      return;
    }
    status.textContent = "正在上传，请保持页面打开。保存完成后会自动返回菜谱。";
  });
}
