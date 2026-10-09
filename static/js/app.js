"use strict";

document.addEventListener("DOMContentLoaded", () => {
    if ("serviceWorker" in navigator && window.isSecureContext) {
        navigator.serviceWorker.register("/service-worker.js").catch((error) => {
            console.error("Family Budget Manager service worker registration failed.", error);
        });
    }

    const amountInput = document.querySelector("#amount");
    if (amountInput) {
        amountInput.addEventListener("blur", () => {
            if (amountInput.value) {
                amountInput.value = Number(amountInput.value).toFixed(2);
            }
        });
    }

    const categorySelect = document.querySelector("#category");
    const customCategoryField = document.querySelector("#custom-category-field");
    const customCategoryInput = document.querySelector("#custom_category");
    if (categorySelect && customCategoryField && customCategoryInput) {
        const updateCustomCategoryVisibility = () => {
            const isOther = categorySelect.value === "Other";
            customCategoryField.hidden = !isOther;
            customCategoryInput.required = isOther;
            customCategoryInput.disabled = !isOther;
            if (!isOther) {
                customCategoryInput.value = "";
            }
        };

        categorySelect.addEventListener("change", updateCustomCategoryVisibility);
        updateCustomCategoryVisibility();
    }

    document.querySelectorAll(".delete-form").forEach((form) => {
        form.addEventListener("submit", (event) => {
            const message = form.dataset.confirm;
            if (message && !window.confirm(message)) {
                event.preventDefault();
            }
        });
    });
});
