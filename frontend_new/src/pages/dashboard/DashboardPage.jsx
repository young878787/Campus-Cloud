import styles from "./DashboardPage.module.scss";

export default function DashboardPage() {
  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.greeting}>
          嗨 · lianqianyi <span className={styles.emoji}>🌿</span>
        </h1>
        <p className={styles.subtitle}>歡迎回來，在這裡開始你的任務！</p>
      </div>
    </div>
  );
}
