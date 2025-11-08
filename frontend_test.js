// frontend_test.js — Example API test from frontend
async function testNormalize() {
  const response = await fetch("https://geofixers-backend.onrender.com/normalize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      raw: "Vidhana Soudha, Ambedkar Veedhi, Bengaluru, Karnataka 560001"
    })
  });

  const data = await response.json();
  console.log("Normalized Response:", data);
}

testNormalize();
