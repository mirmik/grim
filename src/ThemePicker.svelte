<script lang="ts">
  import { themePreference, setTheme, type ThemePreference } from './theme';
</script>

<select class="theme-picker" aria-label="Тема оформления" title="Тема оформления"
  value={$themePreference} onchange={event => setTheme(event.currentTarget.value as ThemePreference)}>
  <option value="system">Системная</option>
  <option value="light">Светлая</option>
  <option value="dark">Тёмная</option>
</select>
