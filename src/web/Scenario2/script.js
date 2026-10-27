
const checkoutForm = document.getElementById("checkoutForm");
const checkoutButton = document.getElementById("checkoutButton");
const message = document.getElementById("message");

// Intentionally nonexistent checkout API
const API_URL = "https://api.example.invalid/checkout";

checkoutForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  message.textContent = "";
  message.className = "";
  checkoutButton.disabled = true;

  const order = {
    name: document.getElementById("name").value,
    email: document.getElementById("email").value,
    address: document.getElementById("address").value,
    city: document.getElementById("city").value,
    total: 64.99
  };

  console.log("[Checkout] Submitting order...");
  console.log("[Checkout] API URL:", API_URL);

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(order)
    });

    if (!response.ok) {
      throw new Error(
        `Checkout request failed: HTTP ${response.status}`
      );
    }

    console.log("[Checkout] Order submitted successfully.");
  } catch (error) {
    console.error("[Checkout] API ERROR:", error);

    message.textContent =
      "Checkout failed. Unable to connect to the order server.";
    message.className = "error";
  } finally {
    checkoutButton.disabled = false;
  }
});
