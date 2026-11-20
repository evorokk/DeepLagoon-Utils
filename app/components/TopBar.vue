<template>
  <div class="navbar bg-base-100 shadow-sm">
    <div class="flex-1">
      <NuxtLink to="/" class="btn btn-ghost text-xl">DeepGoon Wiki</NuxtLink>
    </div>
    <div class="flex-none">
      <ul class="menu menu-horizontal gap-1 px-1">
        <li><NuxtLink to="/" active-class="bg-base-200 font-semibold">Главная</NuxtLink></li>
        <li><NuxtLink to="/chem" active-class="bg-base-200 font-semibold">chem</NuxtLink></li>
        <li><NuxtLink to="/vendo" active-class="bg-base-200 font-semibold">vendo</NuxtLink></li>
        <li><NuxtLink to="/search" active-class="bg-base-200 font-semibold">Поиск</NuxtLink></li>
      </ul>
    </div>
  </div>
</template>
