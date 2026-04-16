import styles from "./DashboardPage.module.scss";

export default function DashboardPage() {
  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.greeting}>
          嗨，lianqianyi
        </h1>
        <p className={styles.subtitle}>歡迎回來，很高興再次見到您！</p>
      </div>
    </div>
  );
}
