<template>
  <div class="navbar bg-base-100 shadow-sm">
    <div class="flex-1">
      <NuxtLink to="/" class="btn btn-ghost text-xl">DeepLagoon-Utils</NuxtLink>
    </div>
    <div class="flex-none">
      <ul class="menu menu-horizontal gap-1 px-1">
        <li><NuxtLink to="/" active-class="bg-base-200 font-semibold">Главная</NuxtLink></li>
        <li><NuxtLink to="/chem" active-class="bg-base-200 font-semibold">Химия</NuxtLink></li>
        <li><NuxtLink to="/gasmix" active-class="bg-base-200 font-semibold">Газы</NuxtLink></li>
        <li><NuxtLink to="/vendo" active-class="bg-base-200 font-semibold">Оборудование</NuxtLink></li>
      </ul>
    </div>
  </div>
</template>
