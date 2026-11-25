import OctoPose from "../OctoPose";
import styles from "./Tour.module.scss";

/* 學生篇開場：每一句換一個章魚動作（想、難過、捧著雲、揮手），一句一個心情 */
const POSES = ["think", "sad", "hold-cloud", "wave"];

export default function StudentIntro({ beat }) {
  return (
    <div className={styles.studentIntro}>
      <OctoPose key={beat} name={POSES[beat] ?? "wave"} className={styles.studentPose} />
    </div>
  );
}
