<?php

  // Инициируем сессию

  session_start();

  // Выводим содержимое суперглобального массива $_SESSION

  echo "<pre>";

  print_r($_SESSION);

  echo "</pre>";

?>
