"use strict";

const form = document.querySelector("#recipe-search-form");
const input = document.querySelector("#recipe-find");
const error = document.querySelector("#recipe-search-error");

if (form && input && error) {
  const clearError = () => {
    error.hidden = true;
    input.removeAttribute("aria-invalid");
  };
  input.addEventListener("input", clearError);
  form.addEventListener("submit", (event) => {
    const term = input.value.trim();
    if (!term) {
      event.preventDefault();
      error.hidden = false;
      input.setAttribute("aria-invalid", "true");
      input.focus();
      return;
    }
    input.value = term;
    clearError();
  });
}
