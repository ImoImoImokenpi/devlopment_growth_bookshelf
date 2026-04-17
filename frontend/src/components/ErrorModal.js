import React from "react";

function ErrorModal({ message, onClose }) {
  if (!message) return null;

  return (
    <div style={s.overlay}>
      <div style={s.modal}>
        <h3 style={{ marginBottom: "10px", color: "#c9506a" }}>
          Error
        </h3>

        <p>{message}</p>

        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "20px" }}>
          <button onClick={onClose} style={s.btnPrimary}>
            OK
          </button>
        </div>
      </div>
    </div>
  );
}

const s = {
  overlay: {
    position: "fixed",
    top: 0,
    left: 0,
    width: "100%",
    height: "100%",
    backgroundColor: "rgba(0,0,0,0.4)",
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    zIndex: 1000,
  },
  modal: {
    backgroundColor: "#fff",
    padding: "30px",
    borderRadius: "12px",
    width: "300px",
    boxShadow: "0 20px 40px rgba(0,0,0,0.2)",
  },
  btnPrimary: {
    padding: "8px 18px",
    backgroundColor: "#c9506a",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    cursor: "pointer",
  },
};

export default ErrorModal;