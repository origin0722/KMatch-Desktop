<template>
  <router-view />
</template>

<script setup>
// 触发主题 store 初始化 (应用 dark class + localStorage 读取)
import { useThemeStore } from '@/stores/theme'
useThemeStore()
</script>

<style>
/* 全局 reset: 主题由 styles/theme.css 的 CSS 变量驱动 */
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body, #app { height: 100%; width: 100%; overflow: hidden; }
body {
  font-family: var(--kfont-ui);
  background: var(--kbg);
  color: var(--ktext);
}
</style>
