import React, { useEffect, useState } from "react";
import axios from "../api/axiosConfig";
import { useNavigate } from "react-router-dom";

axios.defaults.baseURL = "http://127.0.0.1:8000/api";

const WalletHome = () => {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [balance, setBalance] = useState(0.0);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);

  // Shared currency for withdraw + send money
  const [currencyTo, setCurrencyTo] = useState("GBP");
  const [currencies, setCurrencies] = useState([]);
  const [walletCurrency, setWalletCurrency] = useState("KES");
  const [updatingWalletCurrency, setUpdatingWalletCurrency] = useState(false);

  // Withdraw
  const [withdrawAmount, setWithdrawAmount] = useState("");
  const [receiverEmail, setReceiverEmail] = useState("");
  const [preview, setPreview] = useState(null);
  const [withdrawMessage, setWithdrawMessage] = useState("");

  // Send money
  const [showTransferForm, setShowTransferForm] = useState(false);
  const [transferRecipient, setTransferRecipient] = useState("");
  const [transferAmount, setTransferAmount] = useState("");
  const [transferPreview, setTransferPreview] = useState(null);
  const [transferProcessing, setTransferProcessing] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) return navigate("/login");

    axios
      .get("/user/profile/", {
        headers: { Authorization: `Bearer ${token}` },
      })
      .then((res) => {
        setUser(res.data);
        setBalance(parseFloat(res.data.wallet_balance) || 0.0);
        setTransactions(res.data.transactions || []);
        if (res.data.wallet_currency) {
          setWalletCurrency(res.data.wallet_currency);
          setCurrencyTo(res.data.wallet_currency);
        }
        setLoading(false);
      })
      .catch(() => {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        navigate("/login");
      });
  }, [navigate]);

  useEffect(() => {
    // load supported currencies
    const token = localStorage.getItem("access_token");
    if (!token) return;
    axios
      .get("/currencies/", { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => {
        setCurrencies(res.data.currencies || []);
      })
      .catch((err) => {
        console.warn("Could not load currencies:", err?.response?.data || err);
      });
  }, []);

// Deposit
  const handleDeposit = async () => {
    const amount = prompt("Enter deposit amount (KES):");
    if (!amount || isNaN(amount) || amount <= 0) {
      return alert("Invalid deposit amount.");
    }

    try {
      const token = localStorage.getItem("access_token");
      const res = await axios.post(
        "/deposit/",
        { amount },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      alert("Deposit successful!");
      setBalance(parseFloat(res.data.new_balance));
      fetchTransactions();
    } catch (err) {
      alert(err.response?.data?.error || "Deposit failed.");
    }
  };

  const fetchTransactions = async () => {
    try {
      const token = localStorage.getItem("access_token");
      const res = await axios.get("/user/profile/", {
        headers: { Authorization: `Bearer ${token}` },
      });
      setTransactions(res.data.transactions || []);
      setBalance(parseFloat(res.data.wallet_balance) || balance);
    } catch (err) {
      console.error("Fetch transactions error:", err);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    navigate("/login");
  };

  // Preview conversion API call
  const fetchConvertPreview = async (amount) => {
    const token = localStorage.getItem("access_token");
    const res = await axios.post(
      "/convert-preview/",
      { amount, currency_to: currencyTo },
      { headers: { Authorization: `Bearer ${token}` } }
    );
    return res.data;
  };

  // Preview conversion before withdraw
  const handlePreviewConversion = async () => {
    if (!withdrawAmount || withdrawAmount <= 0)
      return setWithdrawMessage("Enter a valid amount.");

    try {
      const data = await fetchConvertPreview(withdrawAmount);
      setPreview(data);
      setWithdrawMessage("");
    } catch (err) {
      setWithdrawMessage("Conversion preview failed.");
    }
  };

  // Withdraw
  const handleWithdraw = async () => {
    if (!withdrawAmount || withdrawAmount <= 0)
      return setWithdrawMessage("Enter a valid amount.");
    if (!receiverEmail)
      return setWithdrawMessage("Enter a receiver email.");

    try {
      const token = localStorage.getItem("access_token");
      const res = await axios.post(
        "/withdraw/",
        {
          amount: withdrawAmount,
          currency_to: currencyTo,
          receiver_email: receiverEmail,
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      setWithdrawMessage(
        `Success! Recipient received ${res.data.converted_amount} ${currencyTo}`
      );
      setPreview(null);
      setWithdrawAmount("");
      setReceiverEmail("");
      setBalance(parseFloat(res.data.new_balance));
      fetchTransactions();
    } catch (err) {
      setWithdrawMessage(err.response?.data?.error || "Withdraw failed.");
    }
  };

  const updateWalletCurrency = async (newCurrency) => {
    try {
      setUpdatingWalletCurrency(true);
      const token = localStorage.getItem("access_token");
      const res = await axios.put(
        "/wallet/",
        { currency: newCurrency },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setWalletCurrency(res.data.currency || newCurrency);
      // refresh transactions and balance after currency change
      fetchTransactions();
      alert(`Wallet currency updated to ${newCurrency}`);
    } catch (err) {
      alert(err.response?.data?.error || "Failed to update wallet currency.");
    } finally {
      setUpdatingWalletCurrency(false);
    }
  };

  // Send money
  const handleSendClick = async () => {
    if (transferProcessing) return;

    if (!transferRecipient || !transferAmount || transferAmount <= 0)
      return alert("Enter valid recipient & amount.");

    try {
      setTransferProcessing(true);

      const token = localStorage.getItem("access_token");

      const previewRes = await axios.post(
        "/convert-preview/",
        { amount: transferAmount, currency_to: currencyTo },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      const previewData = {
        converted_amount: previewRes.data.converted_amount,
        rate: previewRes.data.rate,
        currency: currencyTo,
      };

      setTransferPreview(previewData);

      const confirmed = window.confirm(
        `Recipient will receive ${previewData.converted_amount} ${currencyTo} (rate: ${previewData.rate}). Continue?`
      );
      if (!confirmed) return;

      const res = await axios.post(
        "/transfer/",
        {
          recipient: transferRecipient,
          amount: transferAmount,
          currency_to: currencyTo,
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      alert("Transfer successful!");
      setBalance(parseFloat(res.data.sender_balance));

      setTransferRecipient("");
      setTransferAmount("");
      setTransferPreview(null);
      setShowTransferForm(false);
      fetchTransactions();
    } catch (err) {
      alert(err.response?.data?.error || "Transfer failed.");
    } finally {
      setTransferProcessing(false);
    }
  };

  if (loading) return <p style={{ textAlign: "center" }}>Loading wallet...</p>;

  return (
    <div style={styles.container}>
      <h2>Welcome, {user?.username}</h2>

      <div style={styles.balanceCard}>
        <h3>Wallet Balance</h3>
        <p style={styles.balance}>{walletCurrency} {balance.toFixed(2)}</p>
        <div style={{ marginTop: 8 }}>
          <label>Your wallet currency: </label>
          <select
            value={walletCurrency}
            onChange={(e) => setWalletCurrency(e.target.value)}
          >
            {currencies.map((c) => (
              <option key={c.code} value={c.code}>{c.code} - {c.name}</option>
            ))}
          </select>
          <button
            style={{ marginLeft: 8 }}
            onClick={() => updateWalletCurrency(walletCurrency)}
            disabled={updatingWalletCurrency}
          >
            {updatingWalletCurrency ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>

      <div style={styles.actions}>
        <button style={styles.button} onClick={handleDeposit}>
          Deposit
        </button>

        <div style={{ marginTop: 10 }}>
          <label>Currency to send/withdraw: </label>
          <select
            value={currencyTo}
            onChange={(e) => setCurrencyTo(e.target.value)}
          >
            {currencies.map((c) => (
              <option key={c.code} value={c.code}>{c.code}</option>
            ))}
          </select>
        </div>

        {/* Withdraw */}
        <section style={{ marginTop: 20 }}>
          <h3>Withdraw</h3>
          <input
            type="number"
            placeholder={`Amount (${walletCurrency})`}
            value={withdrawAmount}
            onChange={(e) => setWithdrawAmount(e.target.value)}
          />
          <button onClick={handlePreviewConversion}>Preview</button>

          {preview && (
            <div>
              <p>Rate: {preview.rate}</p>
              <p>
                You will get: {preview.converted_amount} {currencyTo}
              </p>
            </div>
          )}

          {withdrawMessage && <p>{withdrawMessage}</p>}
        </section>

        {/* Send Money */}
        <section style={{ marginTop: 20 }}>
          {!showTransferForm ? (
            <button style={styles.button} onClick={() => setShowTransferForm(true)}>
              Send Money
            </button>
          ) : (
            <div style={{ background: "#fff", padding: 15, borderRadius: 8 }}>
              <h4>Send Money</h4>

              <input
                type="text"
                placeholder="Recipient username/email"
                value={transferRecipient}
                onChange={(e) => setTransferRecipient(e.target.value)}
              />
              <input
                type="number"
                placeholder="Amount"
                value={transferAmount}
                onChange={(e) => setTransferAmount(e.target.value)}
              />

              <div style={{ display: "flex", gap: 10 }}>
                <button disabled={transferProcessing} onClick={handleSendClick}>
                  {transferProcessing ? "Sending..." : "Send"}
                </button>
                <button
                  onClick={() => {
                    setShowTransferForm(false);
                    setTransferPreview(null);
                  }}
                >
                  Cancel
                </button>
              </div>

              {transferPreview && (
                <small>
                  Preview: {transferPreview.converted_amount} {currencyTo} (rate:{" "}
                  {transferPreview.rate})
                </small>
              )}
            </div>
          )}
        </section>
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
                <small>
                  {tx.counterparty ? `Party: ${tx.counterparty}` : 'N/A'}
                </small>
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
  container: { maxWidth: 600, margin: "0 auto", padding: 20 },
  balanceCard: {
    background: "#f3f3f3",
    padding: 20,
    borderRadius: 10,
    textAlign: "center",
  },
  balance: { fontSize: 24, fontWeight: "bold" },
  actions: { marginTop: 20 },
  button: {
    padding: "10px 20px",
    marginBottom: 10,
    cursor: "pointer",
  },
  transactions: { marginTop: 30 },

  transactionList: { 
    listStyle: "none",
    padding: 0,
  },

  transactionItem: {
    borderBottom: "1px solid #eee",
    padding: "10px 0",
  },
  logout: {
    marginTop: 20,
    padding: "10px 20px",
    backgroundColor: "#dc3545",
    color: "white",
    border: "none",
    borderRadius: 8,
    cursor: "pointer",
  }
};
  
export default WalletHome;
