import React, { useEffect, useState } from "react";
import axios from "../api/axiosConfig";
import { useNavigate } from "react-router-dom";

axios.defaults.baseURL = "http://127.0.0.1:8000/api"; // Backend base URL

const WalletHome = () => {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [balance, setBalance] = useState(0.0);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);

  // Shared currency selection (Option A)
  const [currencyTo, setCurrencyTo] = useState("GBP");

  // Withdraw flow state
  const [withdrawAmount, setWithdrawAmount] = useState("");
  const [receiverEmail, setReceiverEmail] = useState("");
  const [preview, setPreview] = useState(null); // preview used for Withdraw UI
  const [withdrawMessage, setWithdrawMessage] = useState("");

  // Transfer (send money) flow state
  const [showTransferForm, setShowTransferForm] = useState(false);
  const [transferRecipient, setTransferRecipient] = useState("");
  const [transferAmount, setTransferAmount] = useState("");
  const [transferPreview, setTransferPreview] = useState(null); // preview state for UI only
  const [transferProcessing, setTransferProcessing] = useState(false);

  // Fetch user + wallet + transactions
  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      navigate("/login");
      return;
    }

    axios
      .get("/user/profile/", {
        headers: { Authorization: `Bearer ${token}` },
      })
      .then((res) => {
        setUser(res.data);
        setBalance(parseFloat(res.data.wallet_balance) || 0.0);
        setTransactions(res.data.transactions || []);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Profile fetch error:", err);
        // Clear tokens and redirect to login
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        navigate("/login");
      });
  }, [navigate]);

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    navigate("/login");
  };

  // ----- Deposit Handler -----
  const handleDeposit = async () => {
    const amount = prompt("Enter deposit amount (KES):");
    if (!amount || isNaN(amount) || amount <= 0) {
      return alert("Please enter a valid amount.");
    }

    try {
      const token = localStorage.getItem("access_token");
      const res = await axios.post(
        "/deposit/",
        { amount },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      if (res.data.message === "Deposit successful") {
        alert("Deposit successful ✅");
        setBalance(parseFloat(res.data.new_balance) || balance);
        fetchTransactions(); // Refresh transactions after deposit
      } else {
        alert("Deposit failed ❌");
      }
    } catch (err) {
      console.error("Deposit error:", err);
      alert(err.response?.data?.error || "Deposit failed ❌");
    }
  };

  // Reusable function to refresh transactions (and wallet)
  const fetchTransactions = async () => {
    try {
      const token = localStorage.getItem("access_token");
      const res = await axios.get("/user/profile/", {
        headers: { Authorization: `Bearer ${token}` },
      });
      setTransactions(res.data.transactions || []);
      setBalance(parseFloat(res.data.wallet_balance) || balance);
    } catch (err) {
      console.error("Transaction refresh error:", err);
    }
  };

  // ----- Convert Preview (shared) -----
  // Used by both Withdraw and Send Money previews (Option A)
  const fetchConvertPreview = async (amount) => {
    const token = localStorage.getItem("access_token");
    if (!token) throw new Error("Not authenticated");

    const res = await axios.post(
      "/convert-preview/",
      { amount, currency_to: currencyTo },
      { headers: { Authorization: `Bearer ${token}` } }
    );
    // Expected res.data: { converted_amount, rate, currency_from, currency_to }
    return res.data;
  };

  // ----- Withdraw (preview) -----
  const handlePreviewConversion = async () => {
    if (!withdrawAmount || isNaN(withdrawAmount) || Number(withdrawAmount) <= 0) {
      return setWithdrawMessage("Please enter a valid withdraw amount.");
    }

    try {
      const data = await fetchConvertPreview(withdrawAmount);
      setPreview(data); // show in UI
      setWithdrawMessage("");
    } catch (err) {
      console.error("Preview error:", err);
      setWithdrawMessage(err.response?.data?.error || "Preview failed");
    }
  };

  // Withdraw handler (Confirm and send to external email)
  const handleWithdraw = async () => {
    if (!withdrawAmount || isNaN(withdrawAmount) || Number(withdrawAmount) <= 0) {
      return setWithdrawMessage("Please enter a valid withdraw amount.");
    }
    if (!receiverEmail) return setWithdrawMessage("Please enter receiver email.");

    try {
      const token = localStorage.getItem("access_token");
      const res = await axios.post(
        "/withdraw/",
        { amount: withdrawAmount, currency_to: currencyTo, receiver_email: receiverEmail },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      setWithdrawMessage(
        `Success! Sent KES ${withdrawAmount}. Recipient got ${res.data.converted_amount} ${currencyTo}`
      );
      setPreview(null);
      setWithdrawAmount("");
      setReceiverEmail("");
      setBalance(parseFloat(res.data.new_balance) || balance);
      fetchTransactions();
    } catch (err) {
      console.error("Withdraw error:", err);
      setWithdrawMessage(err.response?.data?.error || "Withdrawal failed");
    }
  };

  // ----- Send Money (Transfer) Handler -----
  // Main fix: always fetch fresh preview, use preview response directly for confirmation
  const handleSendClick = async () => {
    if (transferProcessing) return;

    if (!transferRecipient || !transferAmount || isNaN(transferAmount) || Number(transferAmount) <= 0) {
      return alert("Please provide a valid recipient and amount.");
    }

    const token = localStorage.getItem("access_token");
    if (!token) {
      alert("Not authenticated");
      return;
    }

    try {
      setTransferProcessing(true);

      // Always fetch a fresh preview from backend (don't rely on previous state)
      const previewRes = await axios.post(
        "/convert-preview/",
        { amount: transferAmount, currency_to: currencyTo },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      const previewData = {
        amount: String(transferAmount),
        converted_amount: previewRes.data.converted_amount,
        rate: previewRes.data.rate,
        currency: currencyTo,
      };

      // Update UI preview state (for display if the form stays open)
      setTransferPreview(previewData);

      // IMPORTANT: use previewData directly for confirmation (not transferPreview state)
      const confirmed = window.confirm(
        `Recipient will receive ${previewData.converted_amount} ${currencyTo} (rate: ${previewData.rate}).\nProceed to send?`
      );

      if (!confirmed) {
        setTransferProcessing(false);
        return;
      }

      // Submit transfer to backend
      const res = await axios.post(
        "/transfer/",
        { recipient: transferRecipient, amount: transferAmount, currency_to: currencyTo },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      alert(res.data.message || "Transfer successful");
      setBalance(parseFloat(res.data.sender_balance) || balance);

      // reset form
      setTransferRecipient("");
      setTransferAmount("");
      setTransferPreview(null);
      setShowTransferForm(false);
      fetchTransactions();
    } catch (err) {
      console.error("Transfer error:", err);
      alert(err.response?.data?.error || "Transfer failed.");
    } finally {
      setTransferProcessing(false);
    }
  };

  if (loading) return <p style={{ textAlign: "center" }}>Loading your wallet...</p>;

  return (
    <div style={styles.container}>
      <h2>Welcome, {user?.username || "User"} 👋</h2>

      <div style={styles.balanceCard}>
        <h3>Wallet Balance</h3>
        <p style={styles.balance}>KES {balance.toFixed(2)}</p>
      </div>

      <div style={styles.actions}>
        <button style={styles.button} onClick={handleDeposit}>
          Deposit
        </button>

        {/* Shared currency dropdown (Option A) */}
        <div style={{ display: "flex", gap: 8, alignItems: "center", justifyContent: "center" }}>
          <label style={{ fontSize: 14 }}>Currency to send/withdraw:</label>
          <select value={currencyTo} onChange={(e) => setCurrencyTo(e.target.value)}>
            <option value="GBP">GBP</option>
            <option value="USD">USD</option>
            <option value="KES">KES</option>
          </select>
        </div>

        {/* Withdraw Section */}
        <section className="withdraw-section" style={{ marginTop: 12 }}>
          <h3>Withdraw Funds</h3>

          <input
            type="email"
            placeholder="Receiver Email"
            value={receiverEmail}
            onChange={(e) => setReceiverEmail(e.target.value)}
          />

          <input
            type="number"
            placeholder="Amount (KES)"
            value={withdrawAmount}
            onChange={(e) => setWithdrawAmount(e.target.value)}
          />

          <button onClick={handlePreviewConversion}>Preview Conversion</button>

          {preview && (
            <div>
              <p>Rate: {preview.rate}</p>
              <p>
                Recipient will receive: {preview.converted_amount} {currencyTo}
              </p>
              <button onClick={handleWithdraw}>Confirm and Send</button>
            </div>
          )}

          {withdrawMessage && <p>{withdrawMessage}</p>}
        </section>

        {/* Send Money Section */}
        <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: 12 }}>
          {!showTransferForm ? (
            <button style={styles.button} onClick={() => setShowTransferForm(true)}>
              Send Money
            </button>
          ) : (
            <div style={{ backgroundColor: "#fff", padding: "12px", borderRadius: 8 }}>
              <h4>Send Money</h4>
              <input
                type="text"
                placeholder="Recipient username or email"
                value={transferRecipient}
                onChange={(e) => setTransferRecipient(e.target.value)}
                style={{ width: "100%", padding: "8px", marginBottom: "8px" }}
              />

              <input
                type="number"
                placeholder={`Amount (${user?.wallet_balance ? "your currency" : ""})`}
                value={transferAmount}
                onChange={(e) => setTransferAmount(e.target.value)}
                style={{ width: "100%", padding: "8px", marginBottom: "8px" }}
              />

              {/* Note: shared currency dropdown is above; keeping it simple here */}
              <div style={{ display: "flex", gap: 8 }}>
                <button style={styles.button} onClick={handleSendClick} disabled={transferProcessing}>
                  {transferProcessing ? "Sending..." : "Send"}
                </button>
                <button
                  style={{ padding: 8 }}
                  onClick={() => {
                    setShowTransferForm(false);
                    setTransferPreview(null);
                  }}
                >
                  Cancel
                </button>
              </div>

              {transferPreview && (
                <div style={{ marginTop: 8 }}>
                  <small>
                    Preview: recipient will receive {transferPreview.converted_amount} {transferPreview.currency} (rate: {transferPreview.rate})
                  </small>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Transaction History */}
      <div style={styles.transactions}>
        <h3>Transaction History</h3>
        {transactions.length === 0 ? (
          <p>No transactions yet.</p>
        ) : (
          <ul style={styles.transactionList}>
            {transactions.map((tx, index) => (
              <li key={index} style={styles.transactionItem}>
                <span>
                  {tx.transaction_type}: <strong>KES {tx.amount}</strong>
                </span>
                <br />
                <small>{tx.description}</small>
                <br />
                <small style={{ color: "#666" }}>{tx.timestamp}</small>
              </li>
            ))}
          </ul>
        )}
      </div>

      <button onClick={handleLogout} style={styles.logout}>
        Logout
      </button>
    </div>
  );
};

const styles = {
  container: {
    maxWidth: "500px",
    margin: "50px auto",
    textAlign: "center",
    backgroundColor: "#f9f9f9",
    padding: "30px",
    borderRadius: "12px",
    boxShadow: "0 4px 10px rgba(0,0,0,0.1)",
  },
  balanceCard: {
    backgroundColor: "#fff",
    padding: "20px",
    borderRadius: "10px",
    marginBottom: "20px",
    boxShadow: "0 2px 6px rgba(0,0,0,0.1)",
  },
  balance: {
    fontSize: "28px",
    color: "#008000",
    margin: "10px 0",
  },
  actions: {
    display: "flex",
    flexDirection: "column",
    gap: "10px",
    marginBottom: "20px",
  },
  button: {
    padding: "10px",
    backgroundColor: "#007bff",
    color: "white",
    border: "none",
    borderRadius: "8px",
    cursor: "pointer",
  },
  logout: {
    backgroundColor: "#dc3545",
    color: "#fff",
    padding: "10px 15px",
    border: "none",
    borderRadius: "8px",
    cursor: "pointer",
  },
  transactions: {
    backgroundColor: "#fff",
    padding: "20px",
    borderRadius: "10px",
    textAlign: "left",
  },
  transactionList: {
    listStyle: "none",
    padding: 0,
  },
  transactionItem: {
    borderBottom: "1px solid #eee",
    padding: "10px 0",
  },
};

export default WalletHome;
