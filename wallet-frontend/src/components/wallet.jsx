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
  const [withdrawAmount, setWithdrawAmount] = useState("");
  const [receiverEmail, setReceiverEmail] = useState("");
  const [currencyTo, setCurrencyTo] = useState("GBP");
  const [preview, setPreview] = useState(null);
  const [withdrawMessage, setWithdrawMessage] = useState("");
  const [showTransferForm, setShowTransferForm] = useState(false);
  const [transferRecipient, setTransferRecipient] = useState("");
  const [transferAmount, setTransferAmount] = useState("");
  const [transferPreview, setTransferPreview] = useState(null);
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
        // Clear our actual token keys and redirect to login
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
  // ----- Transfer Handler (inline form, single Send button) -----
  const handleSendClick = async () => {
    if (transferProcessing) return;

    if (!transferRecipient || !transferAmount || isNaN(transferAmount) || transferAmount <= 0) {
      return alert("Please provide a valid recipient and amount.");
    }

    const token = localStorage.getItem("access_token");

    try {
      setTransferProcessing(true);

      // If we don't already have a preview for these values, request one
      if (!transferPreview || transferPreview.amount !== String(transferAmount) || transferPreview.currency !== currencyTo) {
        const previewRes = await axios.post(
          "/convert-preview/",
          { amount: transferAmount, currency_to: currencyTo },
          { headers: { Authorization: `Bearer ${token}` } }
        );

        setTransferPreview({
          amount: String(transferAmount),
          converted_amount: previewRes.data.converted_amount,
          rate: previewRes.data.rate,
          currency: currencyTo,
        });
      }

      // Confirm with the user using the preview
      const confirmed = window.confirm(
        `Recipient will receive ${transferPreview?.converted_amount || '...'} ${currencyTo} (rate: ${transferPreview?.rate || '...'}).\nProceed to send?`
      );

      if (!confirmed) {
        setTransferProcessing(false);
        return;
      }

      // Submit transfer to backend (transfer/ maps to TransactionFlowView)
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
        setBalance(parseFloat(res.data.new_balance));
        fetchTransactions(); // Refresh transactions after deposit
      } else {
        alert("Deposit failed ❌");
      }
    } catch (err) {
      console.error("Deposit error:", err);
      alert(err.response?.data?.error || "Deposit failed ❌");
    }
  };

  // Reusable function to refresh transactions
  const fetchTransactions = async () => {
    try {
      const token = localStorage.getItem("access_token");
      const res = await axios.get("/user/profile/", {
        headers: { Authorization: `Bearer ${token}` },
      });
      setTransactions(res.data.transactions || []);
    } catch (err) {
      console.error("Transaction refresh error:", err);
    }
  };

  // ----- Withdraw and Convert Handler -----
  const handlePreviewConversion = async () => {
  try {
    const token = localStorage.getItem("access_token");
    const res = await axios.post(
      "/convert-preview/",
      { amount: withdrawAmount, currency_to: currencyTo },
      { headers: { Authorization: `Bearer ${token}` } }
    );
    setPreview(res.data); // { converted_amount, rate }
  } catch (err) {
    setWithdrawMessage(err.response?.data?.error || "Preview failed");
  }
};


// Withdraw handler
const handleWithdraw = async () => {
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
  } catch (err) {
    setWithdrawMessage(err.response?.data?.error || "Withdrawal failed");
  }
};


  // (old prompt-based transfer removed - inline form used instead)


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
        <section className="withdraw-section">
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

  <select
    value={currencyTo}
    onChange={(e) => setCurrencyTo(e.target.value)}
  >
    <option value="GBP">GBP</option>
    <option value="USD">USD</option>
    <option value="KES">KES</option>
  </select>

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

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {!showTransferForm ? (
            <button style={styles.button} onClick={() => setShowTransferForm(true)}>
              Send Money
            </button>
          ) : (
            <div style={{ backgroundColor: '#fff', padding: '12px', borderRadius: 8 }}>
              <h4>Send Money</h4>
              <input
                type="text"
                placeholder="Recipient username or email"
                value={transferRecipient}
                onChange={(e) => setTransferRecipient(e.target.value)}
                style={{ width: '100%', padding: '8px', marginBottom: '8px' }}
              />

              <input
                type="number"
                placeholder={`Amount (${user?.wallet_balance ? 'your currency' : ''})`}
                value={transferAmount}
                onChange={(e) => setTransferAmount(e.target.value)}
                style={{ width: '100%', padding: '8px', marginBottom: '8px' }}
              />

              <select value={currencyTo} onChange={(e) => setCurrencyTo(e.target.value)} style={{ marginBottom: 8 }}>
                <option value="GBP">GBP</option>
                <option value="USD">USD</option>
                <option value="KES">KES</option>
              </select>

              <div style={{ display: 'flex', gap: 8 }}>
                <button style={styles.button} onClick={handleSendClick} disabled={transferProcessing}>
                  {transferProcessing ? 'Sending...' : 'Send'}
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
