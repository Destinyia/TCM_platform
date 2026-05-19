<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="logo">中医四诊数据平台</div>
      <el-menu :default-active="route.path" router background-color="#001529" text-color="#fff">
        <el-menu-item index="/">
          <el-icon><DataAnalysis /></el-icon>
          <span>数据概览</span>
        </el-menu-item>
        <el-menu-item index="/patients">
          <el-icon><User /></el-icon>
          <span>患者管理</span>
        </el-menu-item>
        <el-menu-item index="/checkin-matrix">
          <el-icon><Grid /></el-icon>
          <span>打卡矩阵</span>
        </el-menu-item>
        <el-menu-item index="/examinations">
          <el-icon><Document /></el-icon>
          <span>检查记录</span>
        </el-menu-item>
        <el-menu-item index="/pulse-analysis">
          <el-icon><DataAnalysis /></el-icon>
          <span>脉诊分析</span>
        </el-menu-item>
        <el-menu-item index="/import">
          <el-icon><Upload /></el-icon>
          <span>Demo 数据</span>
        </el-menu-item>
        <el-menu-item index="/export">
          <el-icon><Download /></el-icon>
          <span>数据集版本</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span>{{ currentTitle }}</span>
        <el-dropdown>
          <span class="user-info">管理员 <el-icon><ArrowDown /></el-icon></span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { DataAnalysis, User, Document, Upload, Download, ArrowDown, Grid } from '@element-plus/icons-vue'

const route = useRoute()
const titles = {
  '/': '数据概览',
  '/checkin-matrix': '打卡矩阵',
  '/patients': '用户纵向随访',
  '/examinations': '多模态检查记录',
  '/pulse-analysis': '脉诊横向与纵向分析',
  '/import': '一阶段 Demo 数据',
  '/export': '标准化数据集版本'
}
const currentTitle = computed(() => titles[route.path] || '中医四诊数据平台')
</script>

<style scoped>
.layout { height: 100vh; }
.aside { background: #001529; }
.logo { height: 60px; line-height: 60px; text-align: center; color: #fff; font-size: 16px; font-weight: bold; }
.header { display: flex; justify-content: space-between; align-items: center; background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,.1); }
.user-info { cursor: pointer; }
.main { background: #f0f2f5; }
</style>
