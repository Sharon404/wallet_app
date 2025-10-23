// pages/VerifyOtp.jsx
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";

const VerifyOtp = () => {
  const [otp, setOtp] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleVerify = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage("");

    const user_id = localStorage.getItem("user_id");
    if (!user_id) {
      setMessage("User ID not found. Please log in again.");
      setLoading(false);
      return;
    }

    try {
      const response = await fetch("http://127.0.0.1:8000/api/verify-otp/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id, otp }),
      });

      const data = await response.json();
      if (response.ok) {
        setMessage("OTP verified successfully! Redirecting...");
        setTimeout(() => navigate("/wallet"), 1500);
      } else {
        setMessage(data.error || "Invalid OTP.");
      }
    } catch (error) {
      setMessage("Error verifying OTP. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex justify-center items-center min-h-screen bg-gray-50">
      <div className="bg-white shadow-lg p-8 rounded-2xl w-full max-w-md">
        <h2 className="text-2xl font-semibold text-center mb-6">
          Verify OTP
        </h2>
        <form onSubmit={handleVerify}>
          <label className="block mb-2 text-gray-600">Enter OTP</label>
          <input
            type="text"
            value={otp}
            onChange={(e) => setOtp(e.target.value)}
            required
            className="w-full mb-4 px-3 py-2 border rounded-md focus:ring focus:ring-green-300"
          />

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-green-600 text-white py-2 rounded-md hover:bg-green-700"
          >
            {loading ? "Verifying..." : "Verify OTP"}
          </button>
        </form>

        {message && (
          <p className="text-center mt-4 text-sm text-gray-700">{message}</p>
        )}
      </div>
    </div>
  );
};

export default VerifyOtp;
